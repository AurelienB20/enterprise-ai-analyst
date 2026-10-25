"""On the real data: no company name reaches the provider payload, whatever the query."""

import psycopg
import pytest

from eaa.execution.executor import ReadOnlyExecutor
from eaa.privacy.lineage import LineageResolver
from eaa.privacy.payload import Pseudonymizer, build_payload
from eaa.semantic.model import load
from eaa.sql_security.validator import SQLValidator
from tests.sql_corpus import LEGITIMATE

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def customer_names(migrated_database: str) -> set[str]:
    with psycopg.connect(migrated_database) as connection:
        return {name for (name,) in connection.execute("SELECT customer_name FROM sales.customers")}


@pytest.mark.parametrize("sql", LEGITIMATE.values(), ids=LEGITIMATE.keys())
def test_no_customer_name_reaches_the_provider(
    reader_database_url: str, customer_names: set[str], sql: str
) -> None:
    model = load()
    query = SQLValidator(model).validate(sql)
    result = ReadOnlyExecutor(reader_database_url).execute(query)
    pseudonymizer = Pseudonymizer()

    payload = build_payload(result, LineageResolver(model).resolve(query.sql), pseudonymizer)

    sent = {value for row in payload.rows for value in row if isinstance(value, str)}
    assert not sent & customer_names
    # Whatever was pseudonymised can be put back for the user.
    for (_, value), token in pseudonymizer.tokens.items():
        assert pseudonymizer.reveal(token) == str(value)
