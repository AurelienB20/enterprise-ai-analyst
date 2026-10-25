"""A stand-in for ``anthropic.Anthropic`` that returns scripted, real SDK messages."""

from typing import Any

from anthropic.types.beta import BetaMessage

USAGE = {
    "input_tokens": 300,
    "output_tokens": 120,
    "cache_read_input_tokens": 4_000,
    "cache_creation_input_tokens": 0,
}


def message(content: list[dict[str, Any]], stop_reason: str = "tool_use") -> BetaMessage:
    return BetaMessage.model_validate(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "test-model",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": USAGE,
        }
    )


def submit_query(sql: str, tool_id: str = "toolu_1", **fields: Any) -> BetaMessage:
    payload = {
        "sql": sql,
        "views_used": ["sales_lines"],
        "explanation": "Sums net revenue.",
        "assumptions": [],
        "ambiguities": [],
        **fields,
    }
    return message(
        [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "tool_use", "id": tool_id, "name": "submit_query", "input": payload},
        ]
    )


def cannot_answer(reason: str, text: str, tool_id: str = "toolu_1") -> BetaMessage:
    return message(
        [
            {
                "type": "tool_use",
                "id": tool_id,
                "name": "cannot_answer",
                "input": {"reason": reason, "message": text},
            }
        ]
    )


class _Messages:
    def __init__(self, replies: list[BetaMessage | Exception]) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> BetaMessage:
        # Copy the history: the conversation keeps appending to the same list.
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class _Beta:
    def __init__(self, messages: _Messages) -> None:
        self.messages = messages


class FakeAnthropic:
    def __init__(self, *replies: BetaMessage | Exception) -> None:
        self.beta = _Beta(_Messages(list(replies)))

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.beta.messages.calls


def write_explanation(
    summary: str, key_points: list[str] | None = None, caveats: list[str] | None = None
) -> BetaMessage:
    return message(
        [
            {
                "type": "tool_use",
                "id": "toolu_x",
                "name": "write_explanation",
                "input": {
                    "summary": summary,
                    "key_points": key_points or [],
                    "caveats": caveats or [],
                },
            }
        ]
    )
