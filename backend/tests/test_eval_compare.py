from datetime import date, datetime
from decimal import Decimal

import pytest

from eaa.evaluation.compare import compare, values_equal

D = Decimal


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        (D("1234.56"), D("1234.56")),
        (D("1234.56"), D("1234.564")),
        (D("1234.56"), 1234.56),
        (D("1000000.004"), D("1000000.00")),  # rounding to the cent
        (D("0.4320"), D("43.20")),  # a percentage for a ratio
        (D("0.432046"), D("0.4320")),
        (D("0.432046"), D("43.2")),
        (8, D("8")),
        (date(2025, 8, 1), datetime(2025, 8, 1)),
        ("Printing", " Printing "),
        (None, None),
        (True, True),
    ],
)
def test_equal_values(expected: object, actual: object) -> None:
    assert values_equal(expected, actual)


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        (D("1234.56"), D("1234.60")),
        (D("1000000"), D("1000500")),  # 0.05 % off is a wrong total
        (D("12.5"), D("1250")),  # x100 only applies to ratios
        (D("0.432"), D("0.425")),
        (D("0.432"), D("42.5")),
        (date(2025, 8, 1), datetime(2025, 8, 1, 12)),
        ("Printing", "printing"),
        (None, 0),
        (True, 1),
        ("8", 8),
    ],
)
def test_different_values(expected: object, actual: object) -> None:
    assert not values_equal(expected, actual)


def test_extra_columns_and_other_order_are_fine() -> None:
    expected = [("Western Europe", D("100")), ("Southern Europe", D("50"))]
    actual = [
        (D("50.00"), "Southern Europe", 12),
        (D("100.00"), "Western Europe", 30),
    ]

    assert compare(expected, actual).ok


def test_a_missing_column_or_a_wrong_value_fails() -> None:
    expected = [("Western Europe", D("100"))]

    assert not compare(expected, [("Western Europe",)]).ok
    assert not compare(expected, [("Western Europe", D("101"))]).ok


def test_the_row_count_matters_in_rows_mode() -> None:
    expected = [("a", 1), ("b", 2)]

    result = compare(expected, [("a", 1), ("b", 2), ("c", 3)])

    assert not result.ok and "3 rows" in result.reason
    assert compare(expected, [("c", 3), ("a", 1), ("b", 2)], mode="contains").ok


def test_values_must_line_up_row_by_row() -> None:
    expected = [("a", 1), ("b", 2)]

    # Same values in each column, but swapped between rows.
    assert not compare(expected, [("a", 2), ("b", 1)]).ok


def test_ordered_comparison() -> None:
    expected = [(1, D("10")), (2, D("20"))]

    assert compare(expected, [(1, D("10")), (2, D("20"))], ordered=True).ok
    assert not compare(expected, [(2, D("20")), (1, D("10"))], ordered=True).ok


def test_first_row_mode() -> None:
    expected = [("Printing",)]

    assert compare(expected, [("Printing", D("-0.5")), ("Lighting", D("0.1"))], mode="first").ok
    assert not compare(expected, [("Lighting", D("0.1")), ("Printing", D("-0.5"))], mode="first").ok


def test_empty_results() -> None:
    assert compare([], []).ok
    assert not compare([("a",)], []).ok
