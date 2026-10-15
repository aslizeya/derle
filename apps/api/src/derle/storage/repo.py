"""Data access helpers. All functions take an open cursor so callers control transactions."""

from __future__ import annotations

import json
import re
from typing import Any

import duckdb

from derle.domain.models import DType

Cursor = duckdb.DuckDBPyConnection


def _scalar(cur: Cursor, sql: str, params: list[Any] | None = None) -> Any:
    row = cur.execute(sql, params or []).fetchone()
    return None if row is None else row[0]


def insert_returning_id(cur: Cursor, sql: str, params: list[Any]) -> int:
    value = _scalar(cur, sql + " RETURNING id", params)
    if value is None:
        raise RuntimeError("insert returned no id")
    return int(value)


def allocate_ids(cur: Cursor, n: int) -> list[int]:
    if n == 0:
        return []
    return [
        int(r[0]) for r in cur.execute("SELECT nextval('seq_id') FROM range(?)", [n]).fetchall()
    ]


def bulk_insert(
    cur: Cursor,
    table: str,
    columns: dict[str, list[Any]],
    types: dict[str, str],
) -> None:
    """Insert column-oriented data in one statement.

    Each column is bound as a typed LIST parameter and the lists are zipped with ``unnest``,
    so thousands of rows cost one round trip and no dataframe dependency.
    """
    names = list(columns)
    lengths = {len(v) for v in columns.values()}
    if len(lengths) != 1:
        raise ValueError(f"ragged columns for {table}: {lengths}")
    if lengths == {0}:
        return
    select = ", ".join(f'unnest(CAST(? AS {types[n]}[])) AS "{n}"' for n in names)
    cur.execute(
        f"INSERT INTO {table} ({', '.join(names)}) SELECT {select}",
        [columns[n] for n in names],
    )


# --- workspaces ---------------------------------------------------------------------------


def ensure_default_workspace(cur: Cursor) -> int:
    existing = _scalar(cur, "SELECT id FROM workspaces WHERE NOT is_demo ORDER BY id LIMIT 1")
    if existing is not None:
        return int(existing)
    return insert_returning_id(cur, "INSERT INTO workspaces (name) VALUES (?)", ["Çalışma alanım"])


def create_version(
    cur: Cursor,
    workspace_id: int,
    kind: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> int:
    """Open a new version. ``details`` is structured data the history UI renders in the
    user's language; ``message`` is a plain English fallback for logs."""
    return insert_returning_id(
        cur,
        "INSERT INTO versions (workspace_id, kind, message, details) "
        "VALUES (?, ?, ?, CAST(? AS JSON))",
        [workspace_id, kind, message, to_json(details or {})],
    )


# --- datasets & fields --------------------------------------------------------------------


def dataset_field_keys(cur: Cursor, workspace_id: int) -> dict[int, set[str]]:
    rows = cur.execute(
        "SELECT d.id, f.key FROM datasets d LEFT JOIN fields f ON f.dataset_id = d.id "
        "WHERE d.workspace_id = ?",
        [workspace_id],
    ).fetchall()
    out: dict[int, set[str]] = {}
    for dataset_id, key in rows:
        out.setdefault(int(dataset_id), set())
        if key is not None:
            out[int(dataset_id)].add(key)
    return out


def get_fields(cur: Cursor, dataset_id: int) -> list[dict[str, Any]]:
    rows = cur.execute(
        "SELECT id, key, label, role, dtype, position, pii FROM fields "
        "WHERE dataset_id = ? ORDER BY position",
        [dataset_id],
    ).fetchall()
    keys = ("id", "key", "label", "role", "dtype", "position", "pii")
    return [dict(zip(keys, r, strict=True)) for r in rows]


def view_name(dataset_id: int) -> str:
    return f"ds_{dataset_id}"


def column_name(field_key: str) -> str:
    """Field key -> SQL-friendly column name: "description:urun" -> "description_urun"."""
    return re.sub(r"[^a-z0-9_]", "_", field_key.lower())


_VALUE_COLUMN = {DType.TEXT: "value_text", DType.NUMBER: "value_num", DType.DATE: "value_date"}


def rebuild_dataset_view(cur: Cursor, dataset_id: int) -> None:
    """(Re)create ``ds_<id>``: one typed column per field over current, active records.

    This wide view is what the table UI, dashboards and natural-language queries read.
    """
    fields = get_fields(cur, dataset_id)
    pivots = [
        f"max(CASE WHEN c.field_id = {int(f['id'])} THEN c.{_VALUE_COLUMN[DType(f['dtype'])]} END) "
        f'AS "{column_name(f["key"])}"'
        for f in fields
    ]
    select = ",\n            ".join(["r.id AS record_id", *pivots])
    # Datasets with a party column expose the resolved entity, so queries can group by the
    # real customer ("Ahmet bey" + "A. Yılmaz") instead of by spelling.
    has_party = any(f["role"] == "party" for f in fields)
    entity_cols = ", em.entity_id AS party_id, e.canonical_name AS party_canonical"
    entity_join = (
        "LEFT JOIN entity_members em ON em.record_id = p.record_id AND em.version_to IS NULL "
        "LEFT JOIN entities e ON e.id = em.entity_id"
    )
    cur.execute(
        f"""
        CREATE OR REPLACE VIEW {view_name(dataset_id)} AS
        WITH p AS (
          SELECT
            {select}
          FROM records r
          LEFT JOIN cells c ON c.record_id = r.id AND c.version_to IS NULL
          WHERE r.dataset_id = {int(dataset_id)} AND r.version_to IS NULL
            AND r.status = 'active'
          GROUP BY r.id
        )
        SELECT p.*{entity_cols if has_party else ""}
        FROM p {entity_join if has_party else ""}
        """
    )


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
