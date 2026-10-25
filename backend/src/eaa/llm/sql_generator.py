"""SQL proposals from Claude, through tool calling.

The model answers every question by calling one of two tools with a strict schema:
``submit_query`` (the SQL, the views it uses, an explanation, assumptions, ambiguities)
or ``cannot_answer`` (a reason code and a message). When the backend rejects a query,
the rejection goes back as an error tool_result and the model proposes again, in the
same conversation. The loop itself, and how many attempts it gets, belong to the
pipeline: this module only talks to the model.

Forced tool choice is not available on current models, so tool_choice stays "auto",
the prompt says to always call a tool, and an answer without a tool call is handled.
Server-side fallbacks are on: if a safety classifier declines, the API re-runs the
request on Anthropic's recommended fallback model.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import anthropic
from pydantic import BaseModel, ConfigDict, ValidationError

from eaa.config import Effort

logger = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"

DeclineReason = Literal["personal_data", "not_allowed", "not_in_data", "unclear", "refused"]


class _SubmitQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql: str
    views_used: list[str]
    explanation: str
    assumptions: list[str]
    ambiguities: list[str]


class _CannotAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Literal["personal_data", "not_allowed", "not_in_data", "unclear"]
    message: str


def _strict_tool(name: str, description: str, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


_STRINGS = {"type": "array", "items": {"type": "string"}}
TOOLS: list[dict[str, Any]] = [
    _strict_tool(
        "submit_query",
        "Submit one read-only PostgreSQL query that answers the question.",
        {
            "sql": {"type": "string", "description": "One SELECT statement, no semicolon."},
            "views_used": {**_STRINGS, "description": "Analytics views the query reads."},
            "explanation": {
                "type": "string",
                "description": "One or two sentences: what the query computes and how.",
            },
            "assumptions": {**_STRINGS, "description": "Interpretations you chose."},
            "ambiguities": {**_STRINGS, "description": "Other plausible readings."},
        },
    ),
    _strict_tool(
        "cannot_answer",
        "Use when the question cannot or must not be answered with the analytics views.",
        {
            "reason": {
                "type": "string",
                "enum": ["personal_data", "not_allowed", "not_in_data", "unclear"],
            },
            "message": {"type": "string", "description": "Why, for the user."},
        },
    ),
]


@dataclass(frozen=True)
class QueryProposal:
    sql: str
    views_used: tuple[str, ...]
    explanation: str
    assumptions: tuple[str, ...]
    ambiguities: tuple[str, ...]


@dataclass(frozen=True)
class Declined:
    reason: DeclineReason
    message: str


Proposal = QueryProposal | Declined


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    def add(self, usage: Any) -> None:
        self.calls += 1
        self.input_tokens += usage.input_tokens or 0
        self.output_tokens += usage.output_tokens or 0
        self.cache_read_tokens += usage.cache_read_input_tokens or 0
        self.cache_creation_tokens += usage.cache_creation_input_tokens or 0


class LLMError(Exception):
    """The model could not be reached or gave an unusable answer. ``message`` is safe."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Conversation(Protocol):
    usage: Usage

    def propose(self, feedback: str | None = None) -> Proposal:
        """The next proposal; ``feedback`` explains why the previous one was refused."""
        ...


@dataclass(frozen=True)
class GeneratorConfig:
    model: str
    effort: Effort = "medium"
    max_tokens: int = 16_000
    fallbacks: bool = True


class ClaudeSQLGenerator:
    """Starts one conversation per question. ``client`` is an ``anthropic.Anthropic``."""

    def __init__(self, client: Any, config: GeneratorConfig, system_prompt: str) -> None:
        self._client = client
        self.config = config
        self._system = system_prompt

    def start(self, question: str) -> "ClaudeConversation":
        return ClaudeConversation(self._client, self.config, self._system, question)


@dataclass
class ClaudeConversation:
    client: Any
    config: GeneratorConfig
    system: str
    question: str
    usage: Usage = field(default_factory=Usage)
    messages: list[dict[str, Any]] = field(init=False)
    _pending_tool_use_id: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.messages = [{"role": "user", "content": self.question}]

    def propose(self, feedback: str | None = None) -> Proposal:
        if feedback is not None:
            if self._pending_tool_use_id is None:
                raise RuntimeError("feedback without a previous proposal")
            self.messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": self._pending_tool_use_id,
                            "content": feedback,
                            "is_error": True,
                        }
                    ],
                }
            )
        response = self._create()
        self.usage.add(response.usage)
        # The whole content goes back into the history, thinking blocks included.
        self.messages.append({"role": "assistant", "content": response.content})
        return self._read(response)

    def _create(self) -> Any:
        config = self.config
        extra: dict[str, Any] = (
            {"betas": [FALLBACK_BETA], "fallbacks": "default"} if config.fallbacks else {}
        )
        try:
            return self.client.beta.messages.create(
                model=config.model,
                max_tokens=config.max_tokens,
                output_config={"effort": config.effort},
                system=[
                    {"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}
                ],
                tools=TOOLS,
                tool_choice={"type": "auto", "disable_parallel_tool_use": True},
                messages=self.messages,
                **extra,
            )
        except anthropic.AuthenticationError:
            raise LLMError("The LLM provider rejected the API key.") from None
        except anthropic.RateLimitError:
            raise LLMError("The LLM provider is rate limiting requests.") from None
        except anthropic.BadRequestError as error:
            logger.error("LLM request rejected: %s", error.message)
            raise LLMError("The LLM provider rejected the request.") from None
        except anthropic.APIStatusError as error:
            raise LLMError(f"The LLM provider failed (HTTP {error.status_code}).") from None
        except anthropic.APIConnectionError:
            raise LLMError("The LLM provider could not be reached.") from None

    def _read(self, response: Any) -> Proposal:
        self._pending_tool_use_id = None
        if response.stop_reason == "refusal":
            return Declined("refused", "The model declined to answer this question.")
        if response.stop_reason == "max_tokens":
            raise LLMError("The model ran out of output tokens before answering.")
        tool_uses = [block for block in response.content if block.type == "tool_use"]
        if not tool_uses:
            text = " ".join(b.text for b in response.content if b.type == "text").strip()
            return Declined("unclear", text or "The model gave no answer.")
        tool_use = tool_uses[0]
        self._pending_tool_use_id = tool_use.id
        try:
            if tool_use.name == "submit_query":
                query = _SubmitQuery.model_validate(tool_use.input)
                return QueryProposal(
                    sql=query.sql,
                    views_used=tuple(query.views_used),
                    explanation=query.explanation,
                    assumptions=tuple(query.assumptions),
                    ambiguities=tuple(query.ambiguities),
                )
            if tool_use.name == "cannot_answer":
                declined = _CannotAnswer.model_validate(tool_use.input)
                return Declined(declined.reason, declined.message)
        except ValidationError:
            raise LLMError("The model called a tool with invalid arguments.") from None
        raise LLMError(f"The model called an unknown tool: {tool_use.name}.")
