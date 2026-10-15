"""SQL guard: the only gate between generated SQL and the database.

Whatever produced the SQL (rule templates or an LLM), it must pass this AST check:

* exactly one statement, and it is a query (SELECT / UNION / … / WITH … SELECT)
* every table it reads is an allowed analytics view or one of its own CTEs
* no table functions or file/system functions (``read_csv``, ``glob``, ``getenv``…)
* a row limit is always present

The database is additionally opened with external access disabled (see ``storage.db``),
so the guard is one of two independent layers.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

DEFAULT_LIMIT = 1000

FORBIDDEN_FUNCTIONS = frozenset(
    {
        "read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto",
        "read_text", "read_blob", "parquet_scan", "csv_scan", "glob", "sniff_csv",
        "getenv", "current_setting", "query", "query_table", "load", "install",
    }
)  # fmt: skip
FORBIDDEN_PREFIXES = ("duckdb_", "pragma_", "read_", "sqlite_", "postgres_", "mysql_")


class GuardError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


def _function_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.name).lower()
    return node.sql_name().lower()


def guard_sql(sql: str, allowed_tables: set[str], *, limit: int = DEFAULT_LIMIT) -> str:
    """Validate ``sql`` and return a normalized, limited version of it. Raises GuardError."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except ParseError as exc:
        raise GuardError("parse_error", str(exc)[:200]) from exc
    if len(statements) != 1:
        raise GuardError("multiple_statements")
    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise GuardError("not_select", statement.key)

    allowed = {t.lower() for t in allowed_tables}
    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}

    for table in statement.find_all(exp.Table):
        if isinstance(table.this, exp.Func):
            raise GuardError("function_not_allowed", _function_name(table.this))
        if table.args.get("db") is not None or table.args.get("catalog") is not None:
            raise GuardError("table_not_allowed", table.sql(dialect="duckdb"))
        name = table.name.lower()
        if name not in allowed and name not in cte_names:
            raise GuardError("table_not_allowed", name)

    for func in statement.find_all(exp.Func):
        name = _function_name(func)
        if name in FORBIDDEN_FUNCTIONS or name.startswith(FORBIDDEN_PREFIXES):
            raise GuardError("function_not_allowed", name)

    for node in statement.walk():
        if isinstance(
            node, exp.Insert | exp.Update | exp.Delete | exp.Create | exp.Drop | exp.Command
        ):
            raise GuardError("not_select", node.key)

    existing = statement.args.get("limit")
    if existing is None:
        statement = statement.limit(limit)
    return statement.sql(dialect="duckdb", pretty=True)
