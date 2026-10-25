"""Question -> SQL proposal -> validation -> read-only execution -> verifiable result.

The LLM proposes, the backend verifies, the database enforces permissions. This module
is the only place where the three meet, as a plain loop: at most ``max_attempts``
proposals, each validated and run; a rejection goes back to the model with a reason it
can act on. No result row is ever sent to the model at this stage.

Personal data typed into the question (emails, phone numbers...) is masked before the
question reaches the model or the audit trail. Each result column gets the
classification of the view columns it comes from (eaa.privacy.lineage).

Database error messages go back to the model only when they cannot carry a data value:
a conversion error ("invalid input syntax for type integer: <value>") is replaced by a
generic message, so a value from the views never travels to the provider this way.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Literal, Protocol

from eaa.analysis.explainer import Insight
from eaa.execution.executor import (
    ExecutionError,
    PermissionDeniedError,
    QueryResult,
    QueryTimeoutError,
)
from eaa.llm.sql_generator import (
    Conversation,
    Declined,
    LLMError,
    QueryProposal,
    Usage,
)
from eaa.privacy.lineage import ColumnLineage, LineageResolver
from eaa.privacy.pii import mask_personal_data
from eaa.sql_security.validator import SQLRejectedError, SQLValidator, ValidatedQuery

logger = logging.getLogger(__name__)

Status = Literal["answered", "declined", "rejected", "failed"]
Outcome = Literal["accepted", "rejected", "failed"]


class Executor(Protocol):
    def execute(self, query: ValidatedQuery) -> QueryResult: ...


class ConversationFactory(Protocol):
    def start(self, question: str) -> Conversation: ...


class Explainer(Protocol):
    def explain(
        self,
        question: str,
        sql: str,
        assumptions: list[str],
        result: QueryResult,
        lineage: tuple[ColumnLineage, ...],
    ) -> Insight: ...


@dataclass(frozen=True)
class Prices:
    """USD per million tokens."""

    input: float
    output: float
    cache_read: float

    def cost(self, usage: Usage) -> float:
        uncached = usage.input_tokens
        return round(
            (
                uncached * self.input
                + usage.cache_read_tokens * self.cache_read
                + usage.cache_creation_tokens * self.input * 1.25
                + usage.output_tokens * self.output
            )
            / 1_000_000,
            6,
        )


@dataclass(frozen=True)
class Attempt:
    sql: str
    outcome: Outcome
    message: str | None = None


@dataclass
class Analysis:
    question: str
    model: str
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    status: Status = "failed"
    attempts: list[Attempt] = field(default_factory=list)
    proposal: QueryProposal | None = None
    executed: ValidatedQuery | None = None
    result: QueryResult | None = None
    declined: Declined | None = None
    error_kind: str | None = None
    error_message: str | None = None
    generation_ms: float = 0.0
    execution_ms: float = 0.0
    total_ms: float = 0.0
    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0
    # Kinds of personal data masked in the question ("EMAIL", "PHONE"...).
    masked_personal_data: tuple[str, ...] = ()
    lineage: tuple[ColumnLineage, ...] = ()
    insight: Insight | None = None
    explanation_ms: float = 0.0


def feedback_for_rejection(error: SQLRejectedError) -> str:
    return (
        f"The query was rejected by the validator ({error.reason}): {error.message} "
        "Submit a corrected query with submit_query, or call cannot_answer."
    )


def feedback_for_database_error(error: ExecutionError) -> str:
    if isinstance(error, QueryTimeoutError):
        detail = f"it took longer than the time limit ({error.message})"
    elif error.sqlstate is not None and error.sqlstate.startswith("22"):
        # Data exceptions may quote a value from the data: keep the class, drop the text.
        detail = (
            f"a value could not be converted or computed (SQLSTATE {error.sqlstate}); "
            "check casts, divisions and date arithmetic"
        )
    else:
        detail = error.message
    return (
        f"PostgreSQL could not run the query: {detail}. "
        "Submit a corrected query with submit_query, or call cannot_answer."
    )


class AnalysisPipeline:
    def __init__(
        self,
        generator: ConversationFactory,
        validator: SQLValidator,
        executor: Executor,
        *,
        model: str,
        prices: Prices,
        max_attempts: int = 3,
        lineage: LineageResolver | None = None,
        explainer: Explainer | None = None,
    ) -> None:
        self.generator = generator
        self.lineage = lineage
        self.explainer = explainer
        self.validator = validator
        self.executor = executor
        self.model = model
        self.prices = prices
        self.max_attempts = max_attempts

    def run(self, question: str) -> Analysis:
        """The whole analysis: the answer, then its explanation."""
        analysis = self.answer(question)
        self.explain(analysis)
        return analysis

    def answer(self, question: str) -> Analysis:
        """Question -> SQL -> validated, read-only result. No explanation yet: a caller
        that streams can show the result while the explanation is written."""
        masked = mask_personal_data(question)
        analysis = Analysis(
            question=masked.text, model=self.model, masked_personal_data=masked.kinds
        )
        started = time.perf_counter()
        conversation = self.generator.start(masked.text)
        try:
            self._loop(conversation, analysis)
        except LLMError as error:
            analysis.status = "failed"
            analysis.error_kind = "llm_error"
            analysis.error_message = error.message
        analysis.usage = Usage()
        analysis.usage.merge(conversation.usage)
        analysis.cost_usd = self.prices.cost(analysis.usage)
        analysis.total_ms = round((time.perf_counter() - started) * 1000, 1)
        self._log(analysis, "answered" if analysis.status == "answered" else "ended")
        return analysis

    def explain(self, analysis: Analysis) -> None:
        """Add the checked explanation to an answered analysis, and its cost and time."""
        if analysis.status != "answered" or self.explainer is None:
            return
        self._explain(analysis)
        if analysis.insight is not None:
            analysis.usage.merge(analysis.insight.usage)
            analysis.cost_usd = self.prices.cost(analysis.usage)
            analysis.total_ms = round(analysis.total_ms + analysis.explanation_ms, 1)
            self._log(analysis, "explained")

    def _log(self, analysis: Analysis, step: str) -> None:
        logger.info(
            "Analysis %s %s",
            analysis.status,
            step,
            extra={
                "analysis_id": str(analysis.id),
                "attempts": len(analysis.attempts),
                "llm_calls": analysis.usage.calls,
                "cost_usd": analysis.cost_usd,
                "total_ms": analysis.total_ms,
            },
        )

    def _explain(self, analysis: Analysis) -> None:
        if self.explainer is None or analysis.result is None or analysis.executed is None:
            return
        if not analysis.result.rows:
            return
        started = time.perf_counter()
        analysis.insight = self.explainer.explain(
            analysis.question,
            analysis.executed.sql,
            list(analysis.proposal.assumptions) if analysis.proposal else [],
            analysis.result,
            analysis.lineage,
        )
        analysis.explanation_ms = round((time.perf_counter() - started) * 1000, 1)

    def _loop(self, conversation: Conversation, analysis: Analysis) -> None:
        feedback: str | None = None
        for _ in range(self.max_attempts):
            started = time.perf_counter()
            proposal = conversation.propose(feedback)
            analysis.generation_ms += round((time.perf_counter() - started) * 1000, 1)

            if isinstance(proposal, Declined):
                analysis.status = "declined"
                analysis.declined = proposal
                return
            analysis.proposal = proposal

            try:
                validated = self.validator.validate(proposal.sql)
            except SQLRejectedError as error:
                analysis.attempts.append(Attempt(proposal.sql, "rejected", error.message))
                analysis.status = "rejected"
                analysis.error_kind, analysis.error_message = str(error.reason), error.message
                feedback = feedback_for_rejection(error)
                continue

            started = time.perf_counter()
            try:
                result = self.executor.execute(validated)
            except PermissionDeniedError as error:
                # The validator let through something the role refuses: stop, do not retry.
                analysis.attempts.append(Attempt(validated.sql, "failed", error.message))
                analysis.status = "failed"
                analysis.error_kind, analysis.error_message = error.kind, error.message
                return
            except ExecutionError as error:
                analysis.attempts.append(Attempt(validated.sql, "failed", error.message))
                analysis.status = "failed"
                analysis.error_kind, analysis.error_message = error.kind, error.message
                feedback = feedback_for_database_error(error)
                continue
            finally:
                analysis.execution_ms += round((time.perf_counter() - started) * 1000, 1)

            analysis.attempts.append(Attempt(validated.sql, "accepted"))
            analysis.status = "answered"
            analysis.executed = validated
            analysis.result = result
            if self.lineage is not None:
                analysis.lineage = self.lineage.resolve(validated.sql)
            analysis.error_kind = analysis.error_message = None
            return
