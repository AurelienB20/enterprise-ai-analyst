"""Deterministic validation of LLM-proposed SQL, before anything reaches the database.

The validator parses the query with SQLGlot (PostgreSQL dialect), walks the whole tree
(CTEs, subqueries, set operations, LATERAL) and accepts only a single read query over
the analytics views, calling allowlisted functions. It is an allowlist on purpose: a
denylist of dangerous functions or statements is never complete.

What runs is the SQL **regenerated from the validated tree**, not the original text:
the database executes exactly what was checked, which closes the gap between how SQLGlot
and PostgreSQL might read odd input (comments, quoting tricks).

This is the first layer, not the security boundary: the eaa_reader role is (ADR 0005).
"""

from dataclasses import dataclass
from enum import StrEnum

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError
from sqlglot.optimizer.qualify import qualify

from eaa.semantic.model import SemanticModel

MAX_SQL_LENGTH = 20_000
MAX_NODES = 5_000
ALLOWED_SCHEMA = "analytics"

# Functions an analytical query needs, by SQLGlot name (date_trunc is TIMESTAMP_TRUNC).
# Everything else is refused: pg_sleep, set_config, current_setting, pg_read_file,
# dblink, lo_*, version, current_user, random, now and CURRENT_DATE (the data is frozen
# at the reference date)...
ALLOWED_FUNCTIONS = frozenset(
    {
        # aggregates
        "SUM", "AVG", "COUNT", "MIN", "MAX", "STDDEV", "STDDEV_POP", "STDDEV_SAMP",
        "VARIANCE", "VAR_POP", "VAR_SAMP", "LOGICAL_AND", "LOGICAL_OR", "BOOL_AND",
        "BOOL_OR", "PERCENTILE_CONT", "PERCENTILE_DISC", "MEDIAN", "CORR", "COVAR_POP",
        "COVAR_SAMP", "ARRAY_AGG", "GROUP_CONCAT", "STRING_AGG",
        # window functions
        "ROW_NUMBER", "RANK", "DENSE_RANK", "PERCENT_RANK", "CUME_DIST", "NTILE", "LAG",
        "LEAD", "FIRST_VALUE", "LAST_VALUE", "NTH_VALUE",
        # conditionals and casts
        "CASE", "IF", "COALESCE", "NULLIF", "GREATEST", "LEAST", "CAST", "TRY_CAST",
        # arithmetic
        "ABS", "ROUND", "CEIL", "FLOOR", "TRUNC", "SIGN", "MOD", "POWER", "POW", "SQRT",
        "LN", "LOG", "EXP", "SAFE_DIVIDE",
        # dates
        "TIMESTAMP_TRUNC", "DATE_TRUNC", "EXTRACT", "DATE_PART", "TO_CHAR", "MAKE_DATE",
        "DATE_FROM_PARTS", "AGE", "DATE_ADD", "DATE_SUB", "DATE_DIFF", "DATEDIFF",
        "TS_OR_DS_ADD", "TS_OR_DS_TO_DATE", "TO_DATE", "STR_TO_DATE", "DATE",
        # text
        "LOWER", "UPPER", "INITCAP", "LENGTH", "CONCAT", "CONCAT_WS", "SUBSTRING",
        "TRIM", "LTRIM", "RTRIM", "LEFT", "RIGHT", "REPLACE", "SPLIT_PART", "LPAD", "RPAD",
        "STARTS_WITH",
        # boolean operators and predicates SQLGlot models as functions
        "AND", "OR", "XOR", "EXISTS",
    }
)  # fmt: skip

# Statement and clause types that never belong in a read query, wherever they appear.
FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Drop, exp.Create, exp.Alter,
    exp.TruncateTable, exp.Copy, exp.Command, exp.Grant, exp.Transaction, exp.Commit,
    exp.Rollback, exp.Set, exp.Use, exp.Pragma, exp.LoadData, exp.Into, exp.Lock,
    exp.Placeholder, exp.Parameter, exp.SessionParameter, exp.Revoke, exp.Describe,
    exp.Analyze, exp.Kill, exp.Refresh, exp.Cache, exp.Uncache, exp.Declare,
)  # fmt: skip

READ_ROOTS = (exp.Select, exp.Union, exp.Except, exp.Intersect)


class Rejection(StrEnum):
    EMPTY = "empty"
    TOO_LONG = "too_long"
    PARSE_ERROR = "parse_error"
    MULTIPLE_STATEMENTS = "multiple_statements"
    NOT_A_QUERY = "not_a_query"
    FORBIDDEN_CONSTRUCT = "forbidden_construct"
    FORBIDDEN_TABLE = "forbidden_table"
    FORBIDDEN_FUNCTION = "forbidden_function"
    UNKNOWN_COLUMN = "unknown_column"


class SQLRejectedError(Exception):
    """The query was refused before reaching the database. ``message`` is safe to show."""

    def __init__(self, reason: Rejection, message: str) -> None:
        super().__init__(f"{reason}: {message}")
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class ValidatedQuery:
    sql: str  # regenerated from the validated tree: this is what runs
    views: frozenset[str]
    functions: frozenset[str]


class SQLValidator:
    def __init__(self, model: SemanticModel) -> None:
        self.views = frozenset(view.name for view in model.views)
        self.schema: dict[str, object] = {
            ALLOWED_SCHEMA: {
                view.name: {column.name: column.type for column in view.columns}
                for view in model.views
            }
        }

    def validate(self, sql: str) -> ValidatedQuery:
        if not sql.strip():
            raise SQLRejectedError(Rejection.EMPTY, "The query is empty.")
        if len(sql) > MAX_SQL_LENGTH:
            raise SQLRejectedError(
                Rejection.TOO_LONG, f"The query is longer than {MAX_SQL_LENGTH} characters."
            )
        try:
            statements = [s for s in sqlglot.parse(sql, dialect="postgres") if s is not None]
        except ParseError as error:
            raise SQLRejectedError(
                Rejection.PARSE_ERROR, f"The query is not valid SQL: {_first_line(error)}"
            ) from None
        if not statements:
            raise SQLRejectedError(Rejection.EMPTY, "The query is empty.")
        if len(statements) > 1:
            raise SQLRejectedError(Rejection.MULTIPLE_STATEMENTS, "Only one statement is allowed.")
        (tree,) = statements
        if not isinstance(tree, READ_ROOTS):
            raise SQLRejectedError(
                Rejection.NOT_A_QUERY, "Only read queries (SELECT, WITH ... SELECT) are allowed."
            )

        nodes = list(tree.walk())
        if len(nodes) > MAX_NODES:
            raise SQLRejectedError(Rejection.TOO_LONG, "The query is too complex.")
        for node in nodes:
            if isinstance(node, FORBIDDEN_NODES):
                raise SQLRejectedError(
                    Rejection.FORBIDDEN_CONSTRUCT,
                    f"{_describe(node)} is not allowed in a read query.",
                )
        views = self._check_tables(tree)
        functions = self._check_functions(tree)
        self._check_columns(tree)
        return ValidatedQuery(
            sql=tree.sql(dialect="postgres", comments=False), views=views, functions=functions
        )

    def _check_tables(self, tree: exp.Expression) -> frozenset[str]:
        cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
        views: set[str] = set()
        for table in tree.find_all(exp.Table):
            if not isinstance(table.this, exp.Identifier):
                raise SQLRejectedError(
                    Rejection.FORBIDDEN_TABLE,
                    f"Table functions are not allowed: {table.this.sql(dialect='postgres')}.",
                )
            name, schema = table.name.lower(), table.db.lower()
            if table.catalog:
                raise SQLRejectedError(
                    Rejection.FORBIDDEN_TABLE, f"Cross-database reference: {table.sql()}."
                )
            if not schema and name in cte_names:
                continue
            if schema not in ("", ALLOWED_SCHEMA) or name not in self.views:
                raise SQLRejectedError(
                    Rejection.FORBIDDEN_TABLE,
                    f"{table.sql(dialect='postgres')} is not an analytics view. "
                    f"Allowed views: {', '.join(sorted(self.views))}.",
                )
            views.add(name)
        return frozenset(views)

    def _check_functions(self, tree: exp.Expression) -> frozenset[str]:
        used: set[str] = set()
        for function in tree.find_all(exp.Func):
            if isinstance(function, exp.Anonymous):
                name = function.name.upper()
            else:
                name = function.sql_name().upper()
            if name in ("CURRENT_DATE", "CURRENT_TIMESTAMP", "CURRENT_TIME", "NOW"):
                raise SQLRejectedError(
                    Rejection.FORBIDDEN_FUNCTION,
                    f"{name} is not allowed: the data stops at the reference date, "  # noqa: S608
                    "use (SELECT reference_date FROM analytics.dataset_info).",
                )
            if name not in ALLOWED_FUNCTIONS:
                raise SQLRejectedError(
                    Rejection.FORBIDDEN_FUNCTION, f"The function {name} is not allowed."
                )
            used.add(name)
        return frozenset(used)

    def _check_columns(self, tree: exp.Expression) -> None:
        """Every column must exist in the view it comes from: catches hallucinated columns
        with a message the LLM can act on."""
        try:
            qualify(
                tree.copy(),
                schema=self.schema,
                db=ALLOWED_SCHEMA,
                dialect="postgres",
                validate_qualify_columns=True,
                identify=False,
            )
        except OptimizeError as error:
            raise SQLRejectedError(Rejection.UNKNOWN_COLUMN, _first_line(error)) from None


def _first_line(error: Exception) -> str:
    return str(error).splitlines()[0][:300] if str(error) else type(error).__name__


def _describe(node: exp.Expression) -> str:
    if isinstance(node, exp.Into):
        return "SELECT ... INTO"
    if isinstance(node, exp.Lock):
        return "FOR UPDATE / FOR SHARE"
    if isinstance(node, (exp.Placeholder, exp.Parameter, exp.SessionParameter)):
        return "A parameter placeholder"
    return node.key.upper()
