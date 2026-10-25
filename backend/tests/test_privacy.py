from decimal import Decimal

import pytest

from eaa.evaluation.dataset import load_questions
from eaa.execution.executor import QueryResult, ResultColumn
from eaa.privacy.lineage import ColumnLineage, LineageResolver
from eaa.privacy.payload import Pseudonymizer, build_payload
from eaa.privacy.pii import mask_personal_data
from eaa.semantic.model import load
from tests.sql_corpus import LEGITIMATE

# ---------------------------------------------------------------- masking in questions


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("What did jean.dupont@acme.example order?", "EMAIL"),
        ("Call +33 6 12 34 56 78 about it", "PHONE"),
        ("Le client au 06.12.34.56.78", "PHONE"),
        ("Payé depuis FR76 3000 6000 0112 3456 7890 189", "IBAN"),
        ("Carte 4111 1111 1111 1111 refusée", "CARD"),
        ("NIR 1 84 12 75 123 456 78", "NIR"),
    ],
)
def test_identifiers_are_masked(text: str, kind: str) -> None:
    masked = mask_personal_data(text)

    assert masked.kinds == (kind,)
    assert f"[{kind}]" in masked.text


@pytest.mark.parametrize(
    "text",
    [
        "Quel est le chiffre d'affaires net de 2025 ?",
        "Top 10 customers by net revenue over the last 12 months",
        "Combien de commandes entre le 2026-01-01 et le 2026-03-31 ?",
        "Which customers had more than 10,000 euros of revenue?",
        "Show order 3317 and invoice INV-2025-001234",
        "Card-like but invalid: 4111 1111 1111 1112",
    ],
)
def test_business_questions_are_left_alone(text: str) -> None:
    assert mask_personal_data(text).text == text


def test_several_identifiers_are_masked_once_each() -> None:
    masked = mask_personal_data("Email a@b.example or call +33 6 12 34 56 78, a@b.example")

    assert masked.text == "Email [EMAIL] or call [PHONE], [EMAIL]"
    assert len(masked.findings) == 3


def test_names_of_people_are_not_detected() -> None:
    # A known limit, stated in docs/privacy.md: names have no format to match.
    assert mask_personal_data("What did Jean Dupont buy?").findings == ()


# ---------------------------------------------------------------- lineage


@pytest.fixture(scope="module")
def resolver() -> LineageResolver:
    return LineageResolver(load())


def test_lineage_follows_ctes_and_functions(resolver: LineageResolver) -> None:
    columns = resolver.resolve(
        "WITH t AS (SELECT c.customer_name AS who, SUM(s.net_revenue) AS r "
        "FROM sales_lines s JOIN customers c ON c.customer_id = s.customer_id GROUP BY 1) "
        "SELECT who, r, UPPER(who) AS shout, 1 AS one, COUNT(*) AS n FROM t GROUP BY who, r"
    )

    assert [(c.name, c.classification) for c in columns] == [
        ("who", "confidential"),
        ("r", "internal"),
        ("shout", "confidential"),
        ("one", "internal"),
        ("n", "internal"),
    ]
    assert columns[0].sources == ("customers.customer_name",)


def test_public_columns_stay_public(resolver: LineageResolver) -> None:
    (column,) = resolver.resolve("SELECT DISTINCT region FROM customers")

    assert column.classification == "public"


def test_a_star_is_expanded(resolver: LineageResolver) -> None:
    columns = resolver.resolve("SELECT * FROM customers")

    assert [c.name for c in columns][:2] == ["customer_id", "customer_name"]
    assert columns[1].classification == "confidential"


@pytest.mark.parametrize("sql", LEGITIMATE.values(), ids=LEGITIMATE.keys())
def test_lineage_resolves_every_legitimate_query(resolver: LineageResolver, sql: str) -> None:
    assert resolver.resolve(sql)


def test_unresolvable_sql_gives_no_lineage(resolver: LineageResolver) -> None:
    assert resolver.resolve("SELECT FROM WHERE") == ()


# ---------------------------------------------------------------- provider payload

RESULT = QueryResult(
    columns=(
        ResultColumn("customer_name", "text"),
        ResultColumn("region", "text"),
        ResultColumn("revenue", "numeric"),
    ),
    rows=(
        ("Alpha Oak Retail SAS", "Western Europe", Decimal("10.00")),
        ("Nova Pine Health GmbH", "Central Europe", Decimal("8.00")),
        ("Alpha Oak Retail SAS", "Southern Europe", Decimal("2.00")),
    ),
    truncated=False,
    duration_ms=1.0,
)
LINEAGE = (
    ColumnLineage("customer_name", ("customers.customer_name",), "confidential"),
    ColumnLineage("region", ("customers.region",), "public"),
    ColumnLineage("revenue", ("sales_lines.net_revenue",), "internal"),
)


def test_confidential_values_are_pseudonymised_consistently() -> None:
    payload = build_payload(RESULT, LINEAGE, Pseudonymizer())

    assert [row[0] for row in payload.rows] == ["CUSTOMER_001", "CUSTOMER_002", "CUSTOMER_001"]
    assert [row[1:] for row in payload.rows] == [row[1:] for row in RESULT.rows]
    assert payload.pseudonymised_columns == ("customer_name",)
    assert "Alpha Oak" not in repr(payload)


def test_the_mapping_puts_real_names_back_for_the_user() -> None:
    pseudonymizer = Pseudonymizer()
    build_payload(RESULT, LINEAGE, pseudonymizer)

    assert (
        pseudonymizer.reveal("CUSTOMER_001 leads, CUSTOMER_002 follows.")
        == "Alpha Oak Retail SAS leads, Nova Pine Health GmbH follows."
    )


def test_without_lineage_every_column_is_confidential() -> None:
    payload = build_payload(RESULT, (), Pseudonymizer())

    assert payload.pseudonymised_columns == ("customer_name", "region", "revenue")
    assert all(str(value).startswith("ENTITY_") for row in payload.rows for value in row)


def test_pii_columns_are_dropped_and_rows_capped() -> None:
    lineage = (
        ColumnLineage("customer_name", ("x.email",), "pii"),
        *LINEAGE[1:],
    )

    payload = build_payload(RESULT, lineage, Pseudonymizer(), max_rows=2)

    assert payload.columns == ("region", "revenue")
    assert payload.dropped_columns == ("customer_name",)
    assert len(payload.rows) == 2 and payload.total_rows == 3


def test_no_evaluation_question_is_altered_by_masking() -> None:
    for question in load_questions().questions:
        assert mask_personal_data(question.question).text == question.question, question.id
