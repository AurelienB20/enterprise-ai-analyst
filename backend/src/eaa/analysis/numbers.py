"""Every number in an explanation must come from the result or from a computed fact.

Numbers are read from French or English text ("1 234,56", "1,234.56", "43,2 %", "4.2 M€",
"3,6 millions"), each under every plausible reading (is "1,234" one thousand or one
point two?), and a number is verified when one reading matches a known value at the
precision it is written with: "4,2 M€" matches 4 213 097.12, "43 %" matches 0.4321.

Not checked: years, dates, quarter labels (Q3, T3), pseudonyms (CUSTOMER_001), and
integers that appear in the question or the SQL ("top 5", LIMIT 10).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_IGNORED = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"  # ISO dates
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"  # 30/09/2026
    r"|\b[QTqt][1-4]\b"  # quarters
    r"|\b[A-Z]+_\d+\b"  # pseudonyms
    r"|\b(?:19|20)\d{2}\b(?![.,]\d)"  # years
)
_NUMBER = re.compile(
    r"(?<![\w.,])(?P<sign>[-−+])?(?P<body>\d{1,3}(?:[   ,.']\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"\s?(?P<suffix>%|k€|K€|k\b|K\b|M€|M\b|Md€|Md\b|Mds\b|Mrd\b|millions?|milliards?|billions?|thousand)?",
)
_SCALES = {
    "k": 3, "K": 3, "k€": 3, "K€": 3, "thousand": 3,
    "M": 6, "M€": 6, "million": 6, "millions": 6,
    "Md": 9, "Md€": 9, "Mds": 9, "Mrd": 9, "milliard": 9, "milliards": 9,
    "billion": 9, "billions": 9,
}  # fmt: skip


@dataclass(frozen=True)
class Reading:
    value: Decimal
    tolerance: Decimal


@dataclass(frozen=True)
class NumberCheck:
    text: str
    verified: bool


def _readings_of_body(body: str) -> list[tuple[Decimal, int]]:
    """(value, decimals shown) for each way to read the digits."""
    readings: list[tuple[Decimal, int]] = []
    compact = body.replace(" ", " ").replace(" ", " ").replace("'", " ")
    candidates = []
    for thousands, decimal in (
        (" ", ","),
        (" ", "."),
        (",", "."),
        (".", ","),
        ("", ","),
        ("", "."),
    ):
        if thousands and thousands in compact:
            groups = compact.split(decimal)[0].split(thousands)
            if any(len(g) != 3 for g in groups[1:]):
                continue
        text = compact.replace(thousands, "") if thousands else compact
        if text.count(decimal) > 1:
            continue
        integer, _, fraction = text.partition(decimal)
        if not integer.replace(" ", "").isdigit() or (fraction and not fraction.isdigit()):
            continue
        candidates.append((integer.replace(" ", ""), fraction))
    for integer, fraction in candidates:
        try:
            value = Decimal(f"{integer}.{fraction}" if fraction else integer)
        except InvalidOperation:
            continue
        readings.append((value, len(fraction)))
    return list(dict.fromkeys(readings))


def readings(match: re.Match[str]) -> list[Reading]:
    sign = -1 if match["sign"] in ("-", "−") else 1
    suffix = match["suffix"] or ""
    result = []
    for value, decimals in _readings_of_body(match["body"]):
        half_unit = Decimal(5) * Decimal(10) ** (-decimals - 1)
        value *= sign
        if suffix == "%":
            # 43,2 % is the ratio 0.432 or the number 43.2 (a column already in percent).
            result.append(Reading(value / 100, half_unit / 100))
            result.append(Reading(value, half_unit))
        elif suffix in _SCALES:
            factor = Decimal(10) ** _SCALES[suffix]
            result.append(Reading(value * factor, half_unit * factor))
        else:
            result.append(Reading(value, half_unit))
    return result


def _matches(reading: Reading, known: Iterable[Decimal]) -> bool:
    # Signs are compared loosely ("a drop of 12 %" for -0.12). No x100 here: "43" is not
    # 0.43; a percentage is read as a ratio only when the text writes "%" (readings()).
    for value in known:
        # The relative part absorbs the rounding of the reference itself.
        tolerance = max(reading.tolerance, abs(value) * Decimal("1e-9"))
        if abs(abs(reading.value) - abs(value)) <= tolerance:
            return True
    return False


def check_numbers(text: str, known: Iterable[Decimal], exempt: set[int]) -> list[NumberCheck]:
    known = list(known)
    cleaned = _IGNORED.sub(" ", text)
    checks = []
    for match in _NUMBER.finditer(cleaned):
        options = readings(match)
        if not options:
            continue
        is_plain_integer = not match["suffix"] and all(
            r.value == r.value.to_integral_value() for r in options
        )
        if is_plain_integer and int(abs(options[0].value)) in exempt:
            continue
        checks.append(NumberCheck(match.group().strip(), _matches_any(options, known)))
    return checks


def _matches_any(options: list[Reading], known: list[Decimal]) -> bool:
    return any(_matches(option, known) for option in options)


def integers_in(*texts: str) -> set[int]:
    return {int(n) for text in texts for n in re.findall(r"\d+", text)}
