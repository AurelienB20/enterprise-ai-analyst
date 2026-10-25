"""Masking of personal data typed by users into their questions.

The views hold no personal data, but a user can still type some into a question ("what
did jean.dupont@example.com order?"). Before the question goes to the LLM provider or
into the audit trail, recognisable identifiers are replaced by a typed placeholder.

Pattern matching, on purpose: these identifiers have a format (emails, phone numbers,
IBANs, card numbers with a valid Luhn checksum, French social security numbers). Names
of people have none, so they are NOT detected: a statistical recogniser (Presidio with a
spaCy model) would catch some, at the cost of a heavy dependency and false positives on
company names, which the business questions are full of. See docs/privacy.md.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
# International (+33 6 12 34 56 78) or French national (06 12 34 56 78) numbers. Not any
# run of digits: order and invoice numbers are business data.
_PHONE = re.compile(
    r"(?<![\w-])(?:\+\d{1,3}(?:[\s.-]?\(0\))?(?:[\s.-]?\d){8,12}|0[1-9](?:[\s.-]?\d{2}){4})(?!\d)"
)
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?\b")
_CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
# French NIR: sex, year, month, department, commune, order, key (15 digits).
_NIR = re.compile(r"\b[12]\s?\d{2}\s?(?:0[1-9]|1[0-2])\s?(?:\d{2}|2[AB])\s?\d{3}\s?\d{3}\s?\d{2}\b")


def _iban_checksum(candidate: str) -> bool:
    iban = candidate.replace(" ", "")
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(c, 36)) for c in rearranged)
    return int(digits) % 97 == 1


def _luhn(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]
    total = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


@dataclass(frozen=True)
class Finding:
    kind: str
    start: int
    end: int


@dataclass(frozen=True)
class MaskedText:
    text: str
    findings: tuple[Finding, ...]

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted({f.kind for f in self.findings}))


# Most specific first: an IBAN or a card number also looks like a phone number.
_DETECTORS: tuple[tuple[str, re.Pattern[str], Callable[[str], bool]], ...] = (
    ("EMAIL", _EMAIL, lambda _: True),
    ("IBAN", _IBAN, _iban_checksum),
    ("NIR", _NIR, lambda _: True),
    ("CARD", _CARD, _luhn),
    ("PHONE", _PHONE, lambda _: True),
)


def mask_personal_data(text: str) -> MaskedText:
    """Replace each detected identifier by ``[KIND]``. Not a guarantee: see the module doc."""
    findings: list[Finding] = []
    taken: list[tuple[int, int]] = []
    for kind, pattern, accept in _DETECTORS:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < e and end > s for s, e in taken) or not accept(match.group()):
                continue
            findings.append(Finding(kind, start, end))
            taken.append((start, end))
    masked = text
    for finding in sorted(findings, key=lambda f: f.start, reverse=True):
        masked = masked[: finding.start] + f"[{finding.kind}]" + masked[finding.end :]
    return MaskedText(masked, tuple(sorted(findings, key=lambda f: f.start)))
