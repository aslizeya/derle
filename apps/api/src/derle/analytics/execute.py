"""Run analytical SELECTs with a row cap and a time limit."""

from __future__ import annotations

import threading
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb

from derle.storage.db import Database

DEFAULT_TIMEOUT_S = 5.0
DEFAULT_MAX_ROWS = 1000


class QueryTimeoutError(Exception):
    pass


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def run_select(
    db: Database,
    sql: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> tuple[list[str], list[list[Any]], bool]:
    """Return ``(columns, rows, truncated)``. The query is interrupted after ``timeout_s``."""
    with db.read() as cur:
        timer = threading.Timer(timeout_s, cur.interrupt)
        timer.start()
        try:
            result = cur.execute(sql)
            columns = [d[0] for d in result.description or []]
            rows = result.fetchmany(max_rows + 1)
        except duckdb.InterruptException as exc:
            raise QueryTimeoutError from exc
        finally:
            timer.cancel()
    truncated = len(rows) > max_rows
    return columns, [[_jsonable(v) for v in r] for r in rows[:max_rows]], truncated
