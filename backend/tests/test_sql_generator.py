from datetime import date

import anthropic
import httpx2
import pytest

from eaa.llm.prompt import render_system_prompt
from eaa.llm.sql_generator import (
    FALLBACK_BETA,
    TOOLS,
    ClaudeConversation,
    ClaudeSQLGenerator,
    Declined,
    GeneratorConfig,
    LLMError,
    QueryProposal,
)
from eaa.semantic.model import load
from tests.fake_llm import FakeAnthropic, cannot_answer, message, submit_query

CONFIG = GeneratorConfig(model="test-model", effort="medium", max_tokens=8_000)


def start(client: FakeAnthropic, question: str = "Revenue last month?") -> ClaudeConversation:
    return ClaudeSQLGenerator(client, CONFIG, "SYSTEM").start(question)


def test_a_submitted_query_becomes_a_proposal() -> None:
    client = FakeAnthropic(submit_query("SELECT 1", assumptions=["Last month is Sept."]))
    conversation = start(client)

    proposal = conversation.propose()

    assert proposal == QueryProposal(
        sql="SELECT 1",
        views_used=("sales_lines",),
        explanation="Sums net revenue.",
        assumptions=("Last month is Sept.",),
        ambiguities=(),
    )
    assert conversation.usage.calls == 1
    assert conversation.usage.cache_read_tokens == 4_000


def test_the_request_uses_strict_tools_caching_and_fallbacks() -> None:
    client = FakeAnthropic(submit_query("SELECT 1"))
    start(client).propose()

    (call,) = client.calls
    assert call["model"] == "test-model"
    assert call["output_config"] == {"effort": "medium"}
    assert call["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert all(tool["strict"] for tool in call["tools"])
    assert all(tool["input_schema"]["additionalProperties"] is False for tool in TOOLS)
    assert call["system"] == [
        {"type": "text", "text": "SYSTEM", "cache_control": {"type": "ephemeral"}}
    ]
    assert call["betas"] == [FALLBACK_BETA]
    assert call["fallbacks"] == "default"
    assert call["messages"] == [{"role": "user", "content": "Revenue last month?"}]


def test_feedback_goes_back_as_an_error_tool_result() -> None:
    client = FakeAnthropic(
        submit_query("SELECT * FROM sales.customers", tool_id="toolu_A"),
        submit_query("SELECT 1", tool_id="toolu_B"),
    )
    conversation = start(client)
    conversation.propose()

    proposal = conversation.propose("Rejected: not an analytics view.")

    assert isinstance(proposal, QueryProposal) and proposal.sql == "SELECT 1"
    history = client.calls[1]["messages"]
    assert [m["role"] for m in history] == ["user", "assistant", "user"]
    # The assistant turn goes back whole, thinking block included.
    assert [block.type for block in history[1]["content"]] == ["thinking", "tool_use"]
    assert history[2]["content"] == [
        {
            "type": "tool_result",
            "tool_use_id": "toolu_A",
            "content": "Rejected: not an analytics view.",
            "is_error": True,
        }
    ]


def test_cannot_answer_becomes_a_decline() -> None:
    client = FakeAnthropic(cannot_answer("personal_data", "Emails are not available."))

    assert start(client).propose() == Declined("personal_data", "Emails are not available.")


def test_a_refusal_is_a_decline_not_an_error() -> None:
    client = FakeAnthropic(message([], stop_reason="refusal"))

    proposal = start(client).propose()

    assert isinstance(proposal, Declined) and proposal.reason == "refused"


def test_an_answer_without_a_tool_call_is_handled() -> None:
    client = FakeAnthropic(message([{"type": "text", "text": "Which year?"}], "end_turn"))

    assert start(client).propose() == Declined("unclear", "Which year?")


def test_running_out_of_tokens_is_an_error() -> None:
    client = FakeAnthropic(message([], stop_reason="max_tokens"))

    with pytest.raises(LLMError, match="output tokens"):
        start(client).propose()


def test_invalid_tool_arguments_are_an_error() -> None:
    bad = message([{"type": "tool_use", "id": "t", "name": "submit_query", "input": {"x": 1}}])

    with pytest.raises(LLMError, match="invalid arguments"):
        start(FakeAnthropic(bad)).propose()


@pytest.mark.parametrize(
    ("error", "text"),
    [
        (
            anthropic.RateLimitError(
                "rate",
                response=httpx2.Response(429, request=httpx2.Request("POST", "https://x")),
                body=None,
            ),
            "rate limiting",
        ),
        (anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")), "reached"),
    ],
)
def test_provider_errors_become_safe_messages(error: Exception, text: str) -> None:
    with pytest.raises(LLMError, match=text):
        start(FakeAnthropic(error)).propose()


def test_the_system_prompt_describes_every_view_and_metric_but_no_data() -> None:
    model = load()
    prompt = render_system_prompt(model, date(2026, 9, 30))

    assert "Today is the reference date, 2026-09-30" in prompt
    assert "DATE '2026-09-30'" in prompt
    for view in model.views:
        assert f"analytics.{view.name}:" in prompt
        assert all(f"- {column.name} (" in prompt for column in view.columns)
    for metric in model.metrics:
        assert f"- {metric.name}, " in prompt
    assert "customer_contacts" not in prompt
    assert "@" not in prompt
