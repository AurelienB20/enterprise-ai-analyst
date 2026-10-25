from decimal import Decimal

from eaa.evaluation.dataset import Question
from eaa.evaluation.markdown import render_comparison, render_report
from eaa.evaluation.runner import report, run_questions, score, summarize
from eaa.execution.executor import QueryResult, ResultColumn
from eaa.llm.sql_generator import Declined, QueryProposal, Usage
from eaa.orchestrator.pipeline import Analysis, Attempt
from eaa.sql_security.validator import ValidatedQuery

REVENUE = Question(
    id="rev",
    split="dev",
    category="revenue",
    question="Revenue?",
    expect="answer",
    match="first",
    reference_sql="SELECT 1",
)
EMAILS = Question(
    id="emails",
    split="test",
    category="refusal",
    question="Emails?",
    expect="decline",
    accepted_reasons=("personal_data",),
)


def answered(value: Decimal, attempts: int = 1) -> Analysis:
    analysis = Analysis(question="Revenue?", model="m", status="answered")
    analysis.proposal = QueryProposal("SELECT 1", (), "", (), ())
    analysis.executed = ValidatedQuery("SELECT 1", frozenset({"sales_lines"}), frozenset())
    analysis.result = QueryResult((ResultColumn("revenue", "numeric"),), ((value,),), False, 1.0)
    analysis.attempts = [Attempt("SELECT 1", "accepted")] * attempts
    analysis.usage = Usage(calls=attempts, input_tokens=100, output_tokens=10)
    analysis.cost_usd = 0.01
    analysis.total_ms = 1_000.0
    return analysis


def declined(reason: str) -> Analysis:
    analysis = Analysis(question="Emails?", model="m", status="declined")
    analysis.declined = Declined(reason, "No.")  # type: ignore[arg-type]
    analysis.total_ms = 500.0
    return analysis


def reference(sql: str) -> list[tuple[object, ...]]:
    return [(Decimal("123.45"),)]


def test_a_right_answer_is_correct_and_a_wrong_one_is_not() -> None:
    assert score(REVENUE, answered(Decimal("123.45")), reference).correct
    wrong = score(REVENUE, answered(Decimal("120.00")), reference)
    assert not wrong.correct and "first row" in wrong.detail


def test_a_decline_is_correct_only_for_an_accepted_reason() -> None:
    assert score(EMAILS, declined("personal_data"), reference).correct
    assert not score(EMAILS, declined("not_in_data"), reference).correct
    assert not score(EMAILS, answered(Decimal(1)), reference).correct


def test_declining_a_question_that_has_an_answer_is_a_false_refusal() -> None:
    scores = [score(REVENUE, declined("not_in_data"), reference)]

    assert summarize(scores).false_refusal_rate == 1.0
    assert summarize(scores).execution_accuracy == 0.0


def test_the_summary_aggregates_rates_latency_and_cost() -> None:
    scores = [
        score(REVENUE, answered(Decimal("123.45")), reference),
        score(REVENUE, answered(Decimal("123.45"), attempts=2), reference),
        score(EMAILS, declined("personal_data"), reference),
    ]
    summary = summarize(scores)

    assert summary.accuracy == 1.0
    assert summary.first_try_rate == 0.5
    assert summary.correct_refusal_rate == 1.0
    assert summary.cost_total_usd == 0.02
    assert summary.by_split == {"dev": 1.0, "test": 1.0}
    assert summary.latency_p50_ms == 1_000.0


def test_runs_render_as_reports_and_comparisons() -> None:
    def ask(question: str) -> Analysis:
        return answered(Decimal("123.45")) if question == "Revenue?" else declined("unclear")

    scores = run_questions([REVENUE, EMAILS], ask, reference, workers=2)
    config = {
        "label": "a", "split": "all", "model": "m", "effort": "medium", "max_attempts": 3,
        "questions_version": 1, "semantic_version": 1, "commit": "abc", "date": "today",
        "dataset": {"generator_version": "2", "seed": 42, "scale": "small"},
    }  # fmt: skip
    first = report(config, scores)
    second = report(
        {**config, "label": "b"}, [scores[0], score(EMAILS, declined("personal_data"), reference)]
    )

    markdown = render_report(first)
    assert "| Execution accuracy (answers) | 100.0 % |" in markdown
    assert "### emails (declined)" in markdown
    comparison = render_comparison([first, second])
    assert "| emails | wrong | ok |" in comparison
