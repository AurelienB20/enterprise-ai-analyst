"""Alembic environment: online migrations only, with the owner role.

The URL is ``sqlalchemy.url`` when a caller sets it (the tests do), else DATABASE_URL.
Migrations are hand-written SQL: the schema is the product here, so it is written out
rather than generated from ORM models.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from eaa.config import get_settings
from eaa.db import sqlalchemy_url

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

url = config.get_main_option("sqlalchemy.url") or sqlalchemy_url(
    get_settings().require_database_url()
)
engine = create_engine(url, poolclass=pool.NullPool)

with engine.connect() as connection:
    context.configure(connection=connection, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
