from decimal import Decimal

from eaa.analysis.explainer import Insight, ResultExplainer
from eaa.execution.executor import QueryResult, ResultColumn
from eaa.llm.client import GeneratorConfig
from eaa.privacy.lineage import ColumnLineage
from tests.fake_llm import FakeAnthropic, message, write_explanation

CONFIG = GeneratorConfig(model="test-model")
RESULT = QueryResult(
    columns=(ResultColumn("customer_name", "text"), ResultColumn("revenue", "numeric")),
    rows=(
        ("Alpha Oak Retail SAS", Decimal("300000.00")),
        ("Nova Pine Health GmbH", Decimal("100000.00")),
    ),
    truncated=False,
    duration_ms=1.0,
)
LINEAGE = (
    ColumnLineage("customer_name", ("customers.customer_name",), "confidential"),
    ColumnLineage("revenue", ("sales_lines.net_revenue",), "internal"),
)
QUESTION = "Quels sont les 2 meilleurs clients ?"
SQL = "SELECT customer_name, SUM(net_revenue) AS revenue FROM ... LIMIT 2"


def explain(client: FakeAnthropic) -> Insight:
    return ResultExplainer(client, CONFIG).explain(QUESTION, SQL, [], RESULT, LINEAGE)


def test_a_checked_explanation_gets_real_names_back() -> None:
    client = FakeAnthropic(
        write_explanation(
            "CUSTOMER_001 domine avec 300 000 €, soit 75 % du total de 400 000 €.",
            ["CUSTOMER_002 suit avec 0,1 M€."],
        )
    )

    insight = explain(client)

    assert insight.status == "verified"
    assert insight.summary.startswith("Alpha Oak Retail SAS domine")
    assert insight.key_points == ["Nova Pine Health GmbH suit avec 0,1 M€."]
    assert insight.numbers_checked == 4


def test_the_provider_never_sees_company_names() -> None:
    client = FakeAnthropic(write_explanation("CUSTOMER_001 domine."))
    explain(client)

    sent = repr(client.calls[0]["messages"]) + client.calls[0]["system"][0]["text"]
    assert "Alpha Oak" not in sent and "Nova Pine" not in sent
    assert "CUSTOMER_001" in sent
    assert "revenue.share_of_total[row 1] = 0.75" in sent


def test_an_invented_number_is_sent_back_once_then_corrected() -> None:
    client = FakeAnthropic(
        write_explanation("CUSTOMER_001 a progressé de 12 %."),
        write_explanation("CUSTOMER_001 représente 75 % du total."),
    )

    insight = explain(client)

    assert insight.status == "verified"
    assert insight.usage.calls == 2
    feedback = client.calls[1]["messages"][-1]["content"][0]
    assert feedback["is_error"] is True and "12 %" in feedback["content"]


def test_numbers_still_unverified_withhold_the_commentary() -> None:
    client = FakeAnthropic(
        write_explanation("Une hausse de 12 %."),
        write_explanation("Une hausse de 13 %."),
    )

    insight = explain(client)

    assert insight.status == "fallback"
    assert insight.unverified == ["13 %"]
    assert "12" not in insight.summary and "13" not in insight.summary
    assert "2 ligne(s)" in insight.summary


def test_a_refusal_fails_the_explanation_only() -> None:
    insight = explain(FakeAnthropic(message([], stop_reason="refusal")))

    assert insight.status == "failed"


def test_escapes_left_by_the_model_are_undone() -> None:
    # Seen live: accents escaped twice in the tool arguments.
    client = FakeAnthropic(write_explanation("Les cat\u00e9gories baissent de 75 %."))

    assert explain(client).summary == "Les catégories baissent de 75 %."


def test_a_cut_off_explanation_fails_fast_without_a_second_call() -> None:
    cut = message(
        [{"type": "tool_use", "id": "t", "name": "write_explanation", "input": {"summary": "Les"}}],
        stop_reason="max_tokens",
    )
    client = FakeAnthropic(cut)

    insight = explain(client)

    assert insight.status == "failed"
    assert "cut off" in insight.summary
    assert len(client.calls) == 1
