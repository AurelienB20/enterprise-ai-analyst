from decimal import Decimal

import pytest

from eaa.analysis.facts import compute_facts
from eaa.analysis.numbers import check_numbers, integers_in
from eaa.privacy.payload import ProviderPayload

D = Decimal
KNOWN = [D("4213097.12"), D("0.4321"), D("-0.1234"), D("1234.56"), D("42"), D("3617")]


@pytest.mark.parametrize(
    "text",
    [
        "Le chiffre d'affaires atteint 4 213 097,12 €.",
        "Revenue reached 4,213,097.12 EUR.",
        "Soit environ 4,2 M€.",
        "About 4.21 million euros.",
        "Une part de 43,2 %.",
        "A share of 43%.",
        "Une baisse de 12,3 %.",  # -0.1234 written as a drop
        "Le panier moyen est de 1 234,56 €.",
        "42 commandes.",
        "3 617 factures.",
        "Un ratio de 0,43.",
    ],
)
def test_numbers_from_the_data_are_verified(text: str) -> None:
    checks = check_numbers(text, KNOWN, exempt=set())

    assert checks and all(c.verified for c in checks), checks


@pytest.mark.parametrize(
    "text",
    [
        "Le chiffre d'affaires atteint 4 300 000 €.",
        "Soit environ 4,5 M€.",
        "Une part de 47 %.",
        "Le panier moyen est de 1 235,56 €.",
        "43 commandes.",
    ],
)
def test_invented_numbers_are_caught(text: str) -> None:
    checks = check_numbers(text, KNOWN, exempt=set())

    assert any(not c.verified for c in checks), checks


def test_dates_years_quarters_and_pseudonyms_are_not_checked() -> None:
    text = "Au T3 2026 (du 2026-07-01 au 30/09/2026), CUSTOMER_007 mène en Q3."

    assert check_numbers(text, [], exempt=set()) == []


def test_integers_from_the_question_or_the_sql_are_exempt() -> None:
    exempt = integers_in("Quels sont les 5 meilleurs clients ?", "SELECT ... LIMIT 5")

    assert check_numbers("Les 5 premiers clients", [], exempt) == []
    assert not check_numbers("Les 7 premiers clients", [], exempt)[0].verified


def test_facts_are_computed_exactly() -> None:
    payload = ProviderPayload(
        columns=("region", "revenue"),
        rows=(("North", D("300")), ("South", D("100"))),
        total_rows=2,
        pseudonymised_columns=(),
        dropped_columns=(),
    )
    facts = {f.name: f.value for f in compute_facts(payload)}

    assert facts["revenue.total"] == D("400")
    assert facts["revenue.average"] == D("200")
    assert facts["revenue.share_of_total[row 1]"] == D("0.75")
    assert facts["revenue.last_vs_first_change"] == D(100) / D(300) - 1
    assert facts["row_count"] == 2
