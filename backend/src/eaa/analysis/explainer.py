"""A written explanation of a result, in which every number is checked.

1. The result is turned into a provider payload (eaa.privacy.payload): pseudonymised
   company names, at most 50 rows, no personal data.
2. Code computes the facts (eaa.analysis.facts): totals, shares, changes.
3. The model writes a summary, key points and caveats through a strict tool, from the
   payload and the facts only.
4. Every number in the text is checked against the payload values and the facts
   (eaa.analysis.numbers). Unverified numbers go back to the model once. If some are
   still unverified, the explanation is replaced by a deterministic summary: no
   unchecked figure is ever shown.
5. Pseudonyms are replaced by the real names, in the backend, for the user.
"""

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from eaa.analysis.facts import Fact, compute_facts
from eaa.analysis.numbers import NumberCheck, check_numbers, integers_in
from eaa.execution.executor import QueryResult
from eaa.llm.client import (
    GeneratorConfig,
    LLMError,
    Usage,
    clean_text,
    create_message,
    error_result,
    strict_tool,
)
from eaa.privacy.lineage import ColumnLineage
from eaa.privacy.payload import ProviderPayload, Pseudonymizer, build_payload

InsightStatus = Literal["verified", "fallback", "failed"]

SYSTEM = """\
You explain the result of a business query to the person who asked the question. The
backend ran the SQL; you see its result and figures the backend computed from it.

Rules:
1. Use only numbers that appear in the result or in the computed facts. You may round
   them (4 213 097.12 -> "4.2 million"), never compute new ones: if a figure you need is
   not given, describe the result without it. Every number you write is checked.
2. Refer to pseudonymised entities exactly by their token (CUSTOMER_001): the backend
   puts the real names back. Never guess who they are.
3. Describe what the data shows. Do not claim causes: a drop that coincides with
   something is a coincidence until the data shows more. Say "the data does not tell
   why" when it is relevant.
4. If the result was truncated, or the question's assumptions matter, say so in caveats.
5. Write in the language of the question. Summary: two or three sentences. Key points:
   at most four short sentences. Caveats: limits and assumptions, possibly none.
6. Answer by calling write_explanation.
"""

_STRINGS = {"type": "array", "items": {"type": "string"}}
TOOLS = [
    strict_tool(
        "write_explanation",
        "The explanation of the result for the user.",
        {
            "summary": {"type": "string"},
            "key_points": _STRINGS,
            "caveats": _STRINGS,
        },
    )
]


class _Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    key_points: list[str]
    caveats: list[str]


@dataclass
class Insight:
    status: InsightStatus
    summary: str
    key_points: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    numbers_checked: int = 0
    unverified: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    payload: ProviderPayload | None = None  # what was sent, for tests and audits


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)


def render_request(
    question: str, sql: str, assumptions: list[str], payload: ProviderPayload, facts: list[Fact]
) -> str:
    shown = len(payload.rows)
    rows = "\n".join(
        json.dumps([_json(v) for v in row], ensure_ascii=False) for row in payload.rows
    )
    lines = [
        f"Question: {question}",
        f"SQL that ran:\n{sql}",
        "Assumptions made when writing it: " + ("; ".join(assumptions) or "none"),
        f"Result columns: {json.dumps(list(payload.columns), ensure_ascii=False)}",
        f"Result rows ({shown} of {payload.total_rows}"
        + (", truncated" if shown < payload.total_rows else "")
        + "):",
        rows,
        "Computed facts:",
        *(f"- {fact.name} = {fact.value}" for fact in facts),
    ]
    return "\n".join(lines)


def _known_numbers(payload: ProviderPayload, facts: list[Fact]) -> list[Decimal]:
    numbers = [fact.value for fact in facts]
    for row in payload.rows:
        for value in row:
            if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                numbers.append(Decimal(str(value)))
    return numbers


def _looks_french(question: str) -> bool:
    words = set(question.lower().replace("'", " ").split())
    return bool(words & {"le", "la", "les", "quel", "quelle", "quels", "combien", "des", "du"})


def fallback_summary(question: str, payload: ProviderPayload) -> str:
    if _looks_french(question):
        return (
            f"La requête renvoie {payload.total_rows} ligne(s), présentées dans le tableau "
            "avec le SQL exécuté. Le commentaire automatique a été retiré car il citait des "
            "chiffres qui ne figurent pas dans le résultat."
        )
    return (
        f"The query returned {payload.total_rows} row(s), shown in the table with the SQL "
        "that ran. The written commentary was withheld because it quoted figures that are "
        "not in the result."
    )


class ResultExplainer:
    def __init__(self, client: Any, config: GeneratorConfig, *, max_rows: int = 50) -> None:
        self._client = client
        self.config = config
        self.max_rows = max_rows

    def explain(
        self,
        question: str,
        sql: str,
        assumptions: list[str],
        result: QueryResult,
        lineage: tuple[ColumnLineage, ...],
    ) -> Insight:
        pseudonymizer = Pseudonymizer()
        payload = build_payload(result, lineage, pseudonymizer, max_rows=self.max_rows)
        facts = compute_facts(payload)
        known = _known_numbers(payload, facts)
        exempt = integers_in(question, sql)
        usage = Usage()
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": render_request(question, sql, assumptions, payload, facts)}
        ]
        try:
            for attempt in range(2):
                explanation, tool_use_id = self._ask(messages, usage)
                checks = self._check(explanation, known, exempt)
                unverified = [c.text for c in checks if not c.verified]
                if not unverified:
                    return Insight(
                        status="verified",
                        summary=pseudonymizer.reveal(explanation.summary),
                        key_points=[pseudonymizer.reveal(p) for p in explanation.key_points],
                        caveats=[pseudonymizer.reveal(c) for c in explanation.caveats],
                        numbers_checked=len(checks),
                        usage=usage,
                        payload=payload,
                    )
                if attempt == 0:
                    messages.append(
                        error_result(
                            tool_use_id,
                            "These numbers are neither in the result nor in the computed "
                            f"facts: {', '.join(unverified)}. Rewrite the explanation without "
                            "them, using only the given figures.",
                        )
                    )
        except LLMError as error:
            return Insight(status="failed", summary=error.message, usage=usage, payload=payload)
        return Insight(
            status="fallback",
            summary=fallback_summary(question, payload),
            numbers_checked=len(checks),
            unverified=unverified,
            usage=usage,
            payload=payload,
        )

    def _ask(self, messages: list[dict[str, Any]], usage: Usage) -> tuple[_Explanation, str]:
        response = create_message(
            self._client, self.config, system=SYSTEM, tools=TOOLS, messages=messages
        )
        usage.add(response.usage)
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason == "refusal":
            raise LLMError("The model declined to explain this result.")
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses or tool_uses[0].name != "write_explanation":
            raise LLMError("The model did not write an explanation.")
        try:
            explanation = _Explanation.model_validate(tool_uses[0].input)
            cleaned = _Explanation(
                summary=clean_text(explanation.summary),
                key_points=[clean_text(p) for p in explanation.key_points],
                caveats=[clean_text(c) for c in explanation.caveats],
            )
            return cleaned, tool_uses[0].id
        except ValidationError:
            raise LLMError("The model wrote an explanation with invalid fields.") from None

    @staticmethod
    def _check(
        explanation: _Explanation, known: list[Decimal], exempt: set[int]
    ) -> list[NumberCheck]:
        texts = [explanation.summary, *explanation.key_points, *explanation.caveats]
        return [check for text in texts for check in check_numbers(text, known, exempt)]
