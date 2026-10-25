"""The reference answers of the evaluation, checked on the loaded dataset (seed 42)."""

import psycopg
import pytest

from eaa.evaluation.dataset import Question, load_questions
from eaa.execution.executor import ReadOnlyExecutor
from eaa.semantic.model import load
from eaa.sql_security.validator import SQLValidator

pytestmark = pytest.mark.db

ANSWERS = [q for q in load_questions().questions if q.reference_sql]

# The name (or id) each anomaly's entity is known by in the views.
ENTITY_NAMES = {
    "customer": "SELECT customer_name FROM sales.customers WHERE id = %s",
    "category": "SELECT category_name FROM sales.categories WHERE id = %s",
    "supplier": "SELECT supplier_name FROM sales.suppliers WHERE id = %s",
    "product": "SELECT product_name FROM sales.products WHERE id = %s",
    "order": "SELECT %s",
}


@pytest.fixture(scope="module")
def run(reader_database_url: str) -> object:
    validator = SQLValidator(load())
    executor = ReadOnlyExecutor(reader_database_url)
    return lambda sql: executor.execute(validator.validate(sql)).rows


@pytest.mark.parametrize("question", ANSWERS, ids=[q.id for q in ANSWERS])
def test_every_reference_runs_and_returns_rows(run: object, question: Question) -> None:
    rows = run(question.reference_sql)  # type: ignore[operator]

    assert rows, question.id
    assert all(value is not None for value in rows[0]), question.id
    if question.match == "first":
        assert len(rows) == 1, question.id


@pytest.mark.parametrize(
    "question", [q for q in ANSWERS if q.anomaly], ids=[q.id for q in ANSWERS if q.anomaly]
)
def test_anomaly_questions_have_the_anomaly_as_answer(
    run: object, migrated_database: str, question: Question
) -> None:
    with psycopg.connect(migrated_database) as connection:
        row = connection.execute(
            "SELECT entity_type, entity_id FROM sales.dataset_anomalies WHERE code = %s",
            (question.anomaly,),
        ).fetchone()
        assert row is not None
        entity_type, entity_id = row
        if entity_type == "region":
            expected: object = "Southern Europe"
        else:
            name_row = connection.execute(ENTITY_NAMES[entity_type], (entity_id,)).fetchone()
            assert name_row is not None
            expected = name_row[0]

    ((answer,),) = run(question.reference_sql)  # type: ignore[operator]
    assert str(answer) == str(expected), question.id
