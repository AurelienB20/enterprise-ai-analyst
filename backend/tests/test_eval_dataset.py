from collections import Counter

import pytest
from pydantic import ValidationError

from eaa.evaluation.dataset import Question, load_questions
from eaa.semantic.model import load
from eaa.sql_security.validator import SQLValidator


def test_the_question_set_loads_and_is_balanced() -> None:
    questions = load_questions().questions
    splits = Counter(q.split for q in questions)
    expects = Counter(q.expect for q in questions)

    assert len(questions) >= 40
    assert splits["dev"] >= 20 and splits["test"] >= 15
    assert expects["decline"] >= 6
    # Every injected anomaly is the answer to one question.
    assert {q.anomaly for q in questions if q.anomaly} == {
        "A1_CHURNED_KEY_ACCOUNT", "A2_CATEGORY_DROP", "A3_LATE_SUPPLIER",
        "A4_NEGATIVE_MARGIN", "A5_REGION_GROWTH", "A6_UNPAID_CUSTOMER",
        "A7_ONE_OFF_BIG_ORDER", "A8_RETURNS_SPIKE",
    }  # fmt: skip


def test_every_reference_query_passes_the_validator() -> None:
    validator = SQLValidator(load())
    for question in load_questions().questions:
        if question.reference_sql:
            validator.validate(question.reference_sql)


def test_inconsistent_questions_are_rejected() -> None:
    with pytest.raises(ValidationError, match="reference_sql"):
        Question(id="x", split="dev", category="c", question="q?", expect="answer")
    with pytest.raises(ValidationError, match="accepted_reasons"):
        Question(id="x", split="dev", category="c", question="q?", expect="decline")
