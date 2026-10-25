"""One Messages API call, as every part of the backend makes it.

Strict tools, tool_choice auto without parallel calls (forced tool choice is not
available on current models), a cached system prompt, server-side fallbacks, and
provider errors turned into safe messages.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

import anthropic

from eaa.config import Effort

logger = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True)
class GeneratorConfig:
    model: str
    effort: Effort = "medium"
    max_tokens: int = 16_000
    fallbacks: bool = True


class LLMError(Exception):
    """The model could not be reached or gave an unusable answer. ``message`` is safe."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


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

    def merge(self, other: "Usage") -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_creation_tokens += other.cache_creation_tokens


def create_message(
    client: Any,
    config: GeneratorConfig,
    *,
    system: str,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> Any:
    extra: dict[str, Any] = (
        {"betas": [FALLBACK_BETA], "fallbacks": "default"} if config.fallbacks else {}
    )
    try:
        return client.beta.messages.create(
            model=config.model,
            max_tokens=config.max_tokens,
            output_config={"effort": config.effort},
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=tools,
            tool_choice={"type": "auto", "disable_parallel_tool_use": True},
            messages=messages,
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


def strict_tool(name: str, description: str, properties: dict[str, Any]) -> dict[str, Any]:
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


_LITERAL_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")


def clean_text(text: str) -> str:
    """Undo JSON escapes the model sometimes leaves in tool-argument strings.

    Current models may escape non-ASCII characters twice, so that a parsed argument
    reads "cat\\u00e9gories" instead of "catégories". Seen in a live run.
    """
    return _LITERAL_ESCAPE.sub(lambda match: chr(int(match.group(1), 16)), text)


def error_result(tool_use_id: str, text: str) -> dict[str, Any]:
    return {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": tool_use_id, "content": text, "is_error": True}
        ],
    }
