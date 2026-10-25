"""Database tests run against TEST_DATABASE_URL, a disposable database.

The session starts from an empty schema (downgrade to base, then upgrade to head), and
each test that writes data does so in a transaction that is rolled back.
"""

from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from eaa.db import sqlalchemy_url
from eaa.synthetic.generator import TABLE_COLUMNS, generate
from eaa.synthetic.loader import load

BACKEND_DIR = Path(__file__).resolve().parents[2]


class DatabaseTestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    test_database_url: SecretStr | None = None
    test_reader_database_url: SecretStr | None = None


SALES_TABLES = tuple(TABLE_COLUMNS)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = DatabaseTestSettings().test_database_url
    if url is None:
        pytest.fail("TEST_DATABASE_URL is not set (see backend/.env.example)")
    value = url.get_secret_value()
    if not value.rsplit("/", 1)[-1].endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must name a disposable *_test database")
    return value


def alembic_config(url: str) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("sqlalchemy.url", sqlalchemy_url(url))
    config.attributes["configure_logger"] = False
    return config


def load_committed_dataset(url: str) -> None:
    """Seed 42, small scale, committed: what the read-only role tests see."""
    with psycopg.connect(url) as conn:
        load(conn, generate(seed=42, scale="small"), replace=True)


@pytest.fixture(scope="session")
def migrated_database(test_database_url: str) -> str:
    config = alembic_config(test_database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    load_committed_dataset(test_database_url)
    return test_database_url


@pytest.fixture
def connection(migrated_database: str) -> Iterator[psycopg.Connection]:
    """An owner connection whose work is rolled back at the end of the test."""
    with psycopg.connect(migrated_database) as conn:
        yield conn
        conn.rollback()


@pytest.fixture
def empty_connection(connection: psycopg.Connection) -> psycopg.Connection:
    """Like ``connection``, with every sales table emptied inside the transaction."""
    tables = ", ".join(f"sales.{name}" for name in SALES_TABLES)
    connection.execute(f"TRUNCATE {tables}")
    return connection


@pytest.fixture(scope="session")
def reader_database_url(migrated_database: str) -> str:
    url = DatabaseTestSettings().test_reader_database_url
    if url is None:
        pytest.fail("TEST_READER_DATABASE_URL is not set (see backend/.env.example)")
    return url.get_secret_value()


@pytest.fixture
def reader(reader_database_url: str) -> Iterator[psycopg.Connection]:
    """A connection as eaa_reader, the role that will run generated SQL."""
    with psycopg.connect(reader_database_url) as conn:
        yield conn
        conn.rollback()
