"""The pipeline with a scripted model and a fake executor; the validator is the real one."""

from decimal import Decimal

import pytest

from eaa.execution.executor import (
    ExecutionError,
    PermissionDeniedError,
    QueryResult,
    QueryTimeoutError,
    ResultColumn,
)
from eaa.llm.sql_generator import Declined, LLMError, Proposal, QueryProposal, Usage
from eaa.orchestrator.pipeline import AnalysisPipeline, Prices
from eaa.semantic.model import load
from eaa.sql_security.validator import SQLValidator, ValidatedQuery

GOOD_SQL = "SELECT SUM(net_revenue) AS revenue FROM sales_lines"
RESULT = QueryResult(
    columns=(ResultColumn("revenue", "numeric"),),
    rows=((Decimal("123.45"),),),
    truncated=False,
    duration_ms=3.0,
)
PRICES = Prices(input=4.0, output=20.0, cache_read=0.2)


def proposal(sql: str) -> QueryProposal:
    return QueryProposal(sql, ("sales_lines",), "Sums revenue.", ("All time.",), ())


class ScriptedConversation:
    def __init__(self, replies: list[Proposal | Exception]) -> None:
        self.replies = replies
        self.feedback: list[str | None] = []
        self.usage = Usage()

    def propose(self, feedback: str | None = None) -> Proposal:
        self.feedback.append(feedback)
        self.usage.calls += 1
        self.usage.input_tokens += 1_000
        self.usage.output_tokens += 100
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class ScriptedGenerator:
    def __init__(self, *replies: Proposal | Exception) -> None:
        self.conversation = ScriptedConversation(list(replies))

    def start(self, question: str) -> ScriptedConversation:
        return self.conversation


class FakeExecutor:
    def __init__(self, *outcomes: QueryResult | ExecutionError) -> None:
        self.outcomes = list(outcomes)
        self.ran: list[str] = []

    def execute(self, query: ValidatedQuery) -> QueryResult:
        self.ran.append(query.sql)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, ExecutionError):
            raise outcome
        return outcome


@pytest.fixture(scope="module")
def validator() -> SQLValidator:
    return SQLValidator(load())


def pipeline(
    validator: SQLValidator, generator: ScriptedGenerator, executor: FakeExecutor
) -> AnalysisPipeline:
    return AnalysisPipeline(
        generator, validator, executor, model="test-model", prices=PRICES, max_attempts=3
    )


def test_a_valid_proposal_is_validated_run_and_returned(validator: SQLValidator) -> None:
    executor = FakeExecutor(RESULT)
    analysis = pipeline(validator, ScriptedGenerator(proposal(GOOD_SQL)), executor).run("q")

    assert analysis.status == "answered"
    assert analysis.result == RESULT
    assert analysis.executed is not None and analysis.executed.views == {"sales_lines"}
    # What ran is the regenerated SQL, not the proposal's text.
    assert executor.ran == [analysis.executed.sql]
    assert [a.outcome for a in analysis.attempts] == ["accepted"]
    assert analysis.cost_usd == pytest.approx((1_000 * 4 + 100 * 20) / 1e6)


def test_a_rejected_proposal_is_sent_back_and_corrected(validator: SQLValidator) -> None:
    generator = ScriptedGenerator(
        proposal("SELECT email FROM sales.customer_contacts"), proposal(GOOD_SQL)
    )
    analysis = pipeline(validator, generator, FakeExecutor(RESULT)).run("q")

    assert analysis.status == "answered"
    assert [a.outcome for a in analysis.attempts] == ["rejected", "accepted"]
    first, second = generator.conversation.feedback
    assert first is None
    assert second is not None and "forbidden_table" in second
    assert "sales.customer_contacts" in second


def test_attempts_are_capped(validator: SQLValidator) -> None:
    bad = proposal("DELETE FROM customers")
    generator = ScriptedGenerator(bad, bad, bad, proposal(GOOD_SQL))
    executor = FakeExecutor(RESULT)

    analysis = pipeline(validator, generator, executor).run("q")

    assert analysis.status == "rejected"
    assert len(analysis.attempts) == 3
    assert executor.ran == []
    assert analysis.error_kind == "not_a_query"


def test_a_decline_stops_without_running_anything(validator: SQLValidator) -> None:
    executor = FakeExecutor()
    generator = ScriptedGenerator(Declined("personal_data", "Emails are not available."))

    analysis = pipeline(validator, generator, executor).run("Emails of all customers?")

    assert analysis.status == "declined"
    assert analysis.declined == Declined("personal_data", "Emails are not available.")
    assert executor.ran == []


def test_a_permission_error_is_never_retried(validator: SQLValidator) -> None:
    generator = ScriptedGenerator(proposal(GOOD_SQL), proposal(GOOD_SQL))

    analysis = pipeline(validator, generator, FakeExecutor(PermissionDeniedError())).run("q")

    assert analysis.status == "failed"
    assert analysis.error_kind == "permission_denied"
    assert generator.conversation.usage.calls == 1


def test_a_database_error_is_sent_back(validator: SQLValidator) -> None:
    error = ExecutionError("database_error", "column x does not exist", "42703")
    generator = ScriptedGenerator(proposal(GOOD_SQL), proposal(GOOD_SQL))

    analysis = pipeline(validator, generator, FakeExecutor(error, RESULT)).run("q")

    assert analysis.status == "answered"
    feedback = generator.conversation.feedback[1]
    assert feedback is not None and "column x does not exist" in feedback


def test_a_data_error_message_never_reaches_the_model(validator: SQLValidator) -> None:
    # PostgreSQL quotes the offending value: it could be a customer name.
    error = ExecutionError(
        "database_error", 'invalid input syntax for type integer: "Secret Customer SAS"', "22P02"
    )
    generator = ScriptedGenerator(proposal(GOOD_SQL), proposal(GOOD_SQL))

    pipeline(validator, generator, FakeExecutor(error, RESULT)).run("q")

    feedback = generator.conversation.feedback[1]
    assert feedback is not None and "22P02" in feedback
    assert "Secret Customer" not in feedback


def test_a_timeout_asks_for_a_simpler_query(validator: SQLValidator) -> None:
    generator = ScriptedGenerator(proposal(GOOD_SQL), proposal(GOOD_SQL))

    pipeline(validator, generator, FakeExecutor(QueryTimeoutError(5_000), RESULT)).run("q")

    feedback = generator.conversation.feedback[1]
    assert feedback is not None and "time limit" in feedback


def test_a_provider_failure_is_reported_with_its_cost(validator: SQLValidator) -> None:
    generator = ScriptedGenerator(LLMError("The LLM provider could not be reached."))

    analysis = pipeline(validator, generator, FakeExecutor()).run("q")

    assert analysis.status == "failed"
    assert analysis.error_kind == "llm_error"
    assert analysis.usage.calls == 1


def test_cache_reads_and_writes_are_priced() -> None:
    usage = Usage(
        calls=1,
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=10_000,
        cache_creation_tokens=1_000,
    )

    expected = (100 * 4 + 10_000 * 0.2 + 1_000 * 4 * 1.25 + 50 * 20) / 1e6
    assert PRICES.cost(usage) == pytest.approx(expected)
