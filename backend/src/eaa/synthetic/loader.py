"""Load a generated dataset into the sales schema with COPY, in one transaction.

Loading refuses a database that already holds data, unless ``replace`` is set: replacing
empties every sales table first, which is destructive, so the CLI asks for it explicitly.
"""

import psycopg
from psycopg import sql

from eaa.synthetic.generator import Dataset


class DatasetAlreadyLoadedError(RuntimeError):
    pass


def load(connection: psycopg.Connection, dataset: Dataset, *, replace: bool = False) -> None:
    """Load ``dataset`` inside the caller's transaction; the caller commits."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT EXISTS (SELECT 1 FROM sales.dataset_metadata)")
        row = cursor.fetchone()
        if row is not None and row[0]:
            if not replace:
                raise DatasetAlreadyLoadedError(
                    "the sales schema already holds a dataset (use --replace to overwrite it)"
                )
            tables = sql.SQL(", ").join(
                sql.Identifier("sales", name) for name in reversed(dataset.tables)
            )
            cursor.execute(sql.SQL("TRUNCATE {}").format(tables))

        for table in dataset.tables.values():
            statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
                sql.Identifier("sales", table.name),
                sql.SQL(", ").join(sql.Identifier(column) for column in table.columns),
            )
            with cursor.copy(statement) as copy:
                for row in table.rows:
                    copy.write_row(row)
