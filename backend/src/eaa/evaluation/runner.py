"""Run the question set through the pipeline and score every answer.

A question expected to be answered is correct when the pipeline answered and its rows
match the rows of the reference SQL (eaa.evaluation.compare): "it ran" is not enough,
and no LLM judges numbers. A question expected to be declined is correct when the model
called cannot_answer with an accepted reason.
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any

from eaa.evaluation.compare import compare
from eaa.evaluation.dataset import Question
from eaa.orchestrator.pipeline import Analysis

ReferenceRunner = Callable[[str], Sequence[Sequence[object]]]


@dataclass(frozen=True)
class QuestionScore:
    id: str
    split: str
    category: str
    expect: str
    status: str
    correct: bool
    detail: str
    declined_reason: str | None
    attempts: int
    first_try: bool
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: float
    total_ms: float
    executed_sql: str | None
    error_kind: str | None
    error: str | None
    insight_status: str | None = None
    insight_numbers: int = 0
    # Every proposal and why it was refused: where the prompt or the validator can improve.
    attempt_log: tuple[dict[str, str | None], ...] = ()


def score(question: Question, analysis: Analysis, reference: ReferenceRunner) -> QuestionScore:
    declined = analysis.declined
    if question.expect == "decline":
        correct = declined is not None and declined.reason in question.accepted_reasons
        detail = f"declined ({declined.reason})" if declined else f"not declined: {analysis.status}"
    elif analysis.status != "answered" or analysis.result is None:
        correct = False
        detail = f"not answered: {analysis.status}"
    elif question.reference_sql is None:
        raise ValueError(f"{question.id}: no reference SQL")
    else:
        match = compare(
            reference(question.reference_sql),
            analysis.result.rows,
            mode=question.match,
            ordered=question.ordered,
        )
        correct, detail = match.ok, match.reason
    return QuestionScore(
        id=question.id,
        split=question.split,
        category=question.category,
        expect=question.expect,
        status=analysis.status,
        correct=correct,
        detail=detail,
        declined_reason=declined.reason if declined else None,
        attempts=len(analysis.attempts),
        first_try=analysis.status == "answered" and len(analysis.attempts) == 1,
        llm_calls=analysis.usage.calls,
        input_tokens=analysis.usage.input_tokens,
        output_tokens=analysis.usage.output_tokens,
        cache_read_tokens=analysis.usage.cache_read_tokens,
        cost_usd=analysis.cost_usd,
        total_ms=analysis.total_ms,
        executed_sql=analysis.executed.sql if analysis.executed else None,
        error_kind=analysis.error_kind,
        insight_status=analysis.insight.status if analysis.insight else None,
        insight_numbers=analysis.insight.numbers_checked if analysis.insight else 0,
        error=declined.message if declined else analysis.error_message,
        attempt_log=tuple(
            {"outcome": a.outcome, "message": a.message, "sql": a.sql} for a in analysis.attempts
        ),
    )


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))
    return round(ordered[index], 1)


@dataclass(frozen=True)
class Summary:
    questions: int
    accuracy: float | None
    execution_accuracy: float | None
    correct_refusal_rate: float | None
    false_refusal_rate: float | None
    valid_sql_rate: float | None
    first_try_rate: float | None
    permission_violations: int
    explanations_verified_rate: float | None
    latency_p50_ms: float
    latency_p95_ms: float
    cost_total_usd: float
    cost_mean_usd: float
    by_split: dict[str, float | None] = field(default_factory=dict)
    by_category: dict[str, float | None] = field(default_factory=dict)


def summarize(scores: Sequence[QuestionScore]) -> Summary:
    answers = [s for s in scores if s.expect == "answer"]
    declines = [s for s in scores if s.expect == "decline"]
    groups: dict[str, dict[str, list[bool]]] = {
        "split": defaultdict(list),
        "cat": defaultdict(list),
    }
    for s in scores:
        groups["split"][s.split].append(s.correct)
        groups["cat"][s.category].append(s.correct)
    latencies = [s.total_ms for s in scores] or [0.0]
    total_cost = round(sum(s.cost_usd for s in scores), 4)
    return Summary(
        questions=len(scores),
        accuracy=_rate(sum(s.correct for s in scores), len(scores)),
        execution_accuracy=_rate(sum(s.correct for s in answers), len(answers)),
        correct_refusal_rate=_rate(sum(s.correct for s in declines), len(declines)),
        false_refusal_rate=_rate(sum(s.status == "declined" for s in answers), len(answers)),
        valid_sql_rate=_rate(sum(s.status == "answered" for s in answers), len(answers)),
        first_try_rate=_rate(sum(s.first_try for s in answers), len(answers)),
        permission_violations=sum(s.error_kind == "permission_denied" for s in scores),
        explanations_verified_rate=_rate(
            sum(s.insight_status == "verified" for s in scores),
            sum(s.insight_status is not None for s in scores),
        ),
        latency_p50_ms=_percentile(latencies, 0.5),
        latency_p95_ms=_percentile(latencies, 0.95),
        cost_total_usd=total_cost,
        cost_mean_usd=round(total_cost / len(scores), 4) if scores else 0.0,
        by_split={k: _rate(sum(v), len(v)) for k, v in sorted(groups["split"].items())},
        by_category={k: _rate(sum(v), len(v)) for k, v in sorted(groups["cat"].items())},
    )


def run_questions(
    questions: Sequence[Question],
    ask: Callable[[str], Analysis],
    reference: ReferenceRunner,
    *,
    workers: int = 4,
) -> list[QuestionScore]:
    def one(question: Question) -> QuestionScore:
        return score(question, ask(question.question), reference)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, questions))


def report(config: dict[str, Any], scores: Sequence[QuestionScore]) -> dict[str, Any]:
    summary = summarize(scores)
    return {
        "config": config,
        "summary": asdict(summary),
        "statuses": dict(Counter(s.status for s in scores)),
        "questions": [asdict(s) for s in scores],
    }
