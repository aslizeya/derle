"""Read-side queries for the API: datasets, records, provenance."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from derle.normalize.tr.numbers import format_decimal
from derle.normalize.tr.text import fold
from derle.storage import repo
from derle.storage.repo import Cursor


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)  # DECIMAL(18,4) fits a double exactly enough for display
    if isinstance(value, date):
        return value.isoformat()
    return value


def list_datasets(cur: Cursor, workspace_id: int) -> list[dict[str, Any]]:
    rows = cur.execute(
        """
        SELECT d.id, d.name, d.created_at,
               count(r.id) FILTER (WHERE r.status = 'active') AS records,
               count(r.id) FILTER (WHERE r.status = 'duplicate') AS duplicates,
               count(DISTINCT r.table_id) AS sources
        FROM datasets d
        LEFT JOIN records r ON r.dataset_id = d.id AND r.version_to IS NULL
        WHERE d.workspace_id = ?
        GROUP BY d.id, d.name, d.created_at
        ORDER BY d.id
        """,
        [workspace_id],
    ).fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "created_at": r[2].isoformat(),
            "records": r[3],
            "duplicates": r[4],
            "sources": r[5],
        }
        for r in rows
    ]


def get_dataset(cur: Cursor, dataset_id: int) -> dict[str, Any] | None:
    row = cur.execute(
        "SELECT id, workspace_id, name FROM datasets WHERE id = ?", [dataset_id]
    ).fetchone()
    if row is None:
        return None
    fields = repo.get_fields(cur, dataset_id)
    for f in fields:
        f["column"] = repo.column_name(f["key"])
    return {"id": row[0], "workspace_id": row[1], "name": row[2], "fields": fields}


def list_records(
    cur: Cursor,
    dataset_id: int,
    *,
    limit: int,
    offset: int,
    sort: str | None = None,
    descending: bool = False,
    query: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """One page of the clean table. ``sort`` must be a view column (validated, never
    interpolated from user input); ``query`` searches all text columns, Turkish-folded."""
    view = repo.view_name(dataset_id)
    described = cur.execute(f"SELECT * FROM {view} LIMIT 0").description
    columns = {d[0]: str(d[1]) for d in described}

    where, params = "", []
    if query:
        text_cols = [c for c, t in columns.items() if "VARCHAR" in t.upper() or t == "STRING"]
        if text_cols:
            empty = "''"
            haystack = " || ' ' || ".join(f'coalesce("{c}", {empty})' for c in text_cols)
            where = f"WHERE strip_accents(lower(translate({haystack}, 'ıİ', 'iI'))) LIKE ?"
            params.append(f"%{fold(query)}%")

    order = "record_id"
    if sort in columns:
        order = f'"{sort}" {"DESC" if descending else "ASC"} NULLS LAST, record_id'

    total_row = cur.execute(f"SELECT count(*) FROM {view} {where}", params).fetchone()
    total = int(total_row[0]) if total_row else 0
    result = cur.execute(
        f"SELECT * FROM {view} {where} ORDER BY {order} LIMIT ? OFFSET ?",
        [*params, limit, offset],
    )
    names = [d[0] for d in result.description]
    rows = [
        {name: _jsonable(value) for name, value in zip(names, r, strict=True)}
        for r in result.fetchall()
    ]
    return rows, total


def cell_marks(cur: Cursor, record_ids: list[int]) -> dict[int, dict[str, dict[str, Any]]]:
    """Per-cell state for highlighting: ``changed`` (normalized), ``original`` (a change was
    undone, raw text kept) or ``failed`` (could not be parsed). Unchanged cells are omitted."""
    marks: dict[int, dict[str, dict[str, Any]]] = {}
    if not record_ids:
        return marks
    rows = cur.execute(
        """
        SELECT c.record_id, f.key, c.raw_value,
               list(t.kind) FILTER (WHERE t.id IS NOT NULL AND t.undone_in_version IS NULL),
               count(t.id) FILTER (WHERE t.undone_in_version IS NOT NULL)
        FROM cells c
        JOIN fields f ON f.id = c.field_id
        LEFT JOIN transformations t ON t.record_id = c.record_id AND t.field_id = c.field_id
        WHERE c.version_to IS NULL AND c.record_id IN (SELECT unnest(?::BIGINT[]))
        GROUP BY c.record_id, f.key, c.raw_value
        """,
        [record_ids],
    ).fetchall()
    for record_id, key, raw, all_kinds, undone in rows:
        kinds = [k for k in (all_kinds or []) if k != "text_trimmed"]
        if "parse_failed" in kinds:
            state = "failed"
        elif kinds:
            state = "changed"
        elif undone:
            state = "original"
        else:
            continue
        marks.setdefault(int(record_id), {})[repo.column_name(key)] = {
            "state": state,
            "kinds": kinds,
            "raw": raw,
        }
    return marks


def list_uploads(cur: Cursor, workspace_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = cur.execute(
        """
        SELECT u.id, u.filename, u.status, u.error_code, u.created_at, u.size_bytes,
               count(DISTINCT t.id) AS tables,
               count(r.id) FILTER (WHERE r.status = 'active') AS records,
               count(r.id) FILTER (WHERE r.status = 'duplicate') AS duplicates,
               min(t.id) AS first_table, any_value(t.dataset_id) AS dataset_id
        FROM uploads u
        LEFT JOIN upload_tables t ON t.upload_id = u.id
        LEFT JOIN records r ON r.table_id = t.id AND r.version_to IS NULL
        WHERE u.workspace_id = ?
        GROUP BY ALL
        ORDER BY u.id DESC
        LIMIT ?
        """,
        [workspace_id, limit],
    ).fetchall()
    keys = ("id", "filename", "status", "error_code", "created_at", "size_bytes", "tables",
            "records", "duplicates", "first_table_id", "dataset_id")  # fmt: skip
    out = []
    for r in rows:
        item = dict(zip(keys, r, strict=True))
        item["created_at"] = item["created_at"].isoformat()
        out.append(item)
    return out


def workspace_summary(cur: Cursor, workspace_id: int) -> dict[str, Any] | None:
    row = cur.execute(
        "SELECT id, name, is_demo, created_at FROM workspaces WHERE id = ?", [workspace_id]
    ).fetchone()
    if row is None:
        return None
    counts = cur.execute(
        """
        SELECT
          (SELECT count(*) FROM datasets WHERE workspace_id = $ws),
          (SELECT count(*) FROM uploads WHERE workspace_id = $ws AND status = 'done'),
          (SELECT count(*) FROM records r JOIN datasets d ON d.id = r.dataset_id
            WHERE d.workspace_id = $ws AND r.version_to IS NULL AND r.status = 'active'),
          (SELECT count(DISTINCT em.entity_id) FROM entity_members em
            JOIN entities e ON e.id = em.entity_id
            WHERE e.workspace_id = $ws AND em.version_to IS NULL),
          (SELECT count(*) FROM match_candidates WHERE workspace_id = $ws AND status = 'pending')
        """,
        {"ws": workspace_id},
    ).fetchone()
    assert counts is not None
    return {
        "id": row[0],
        "name": row[1],
        "is_demo": row[2],
        "created_at": row[3].isoformat(),
        "datasets": counts[0],
        "uploads": counts[1],
        "records": counts[2],
        "entities": counts[3],
        "pending_matches": counts[4],
    }


def cell_provenance(cur: Cursor, record_id: int, field_id: int) -> dict[str, Any] | None:
    """Where did this value come from? File, sheet, row, original text, applied transforms."""
    row = cur.execute(
        """
        SELECT c.value_text, c.value_num, c.value_date, c.raw_value, c.src_cols,
               r.row_index, r.status, r.duplicate_of, t.sheet, t.header_row, t.id,
               u.id, u.filename, u.created_at, f.key, f.label
        FROM cells c
        JOIN records r ON r.id = c.record_id AND r.version_to IS NULL
        JOIN upload_tables t ON t.id = r.table_id
        JOIN uploads u ON u.id = t.upload_id
        JOIN fields f ON f.id = c.field_id
        WHERE c.record_id = ? AND c.field_id = ? AND c.version_to IS NULL
        """,
        [record_id, field_id],
    ).fetchone()
    if row is None:
        return None
    (text, num, day, raw, src_cols, row_index, status, dup_of, sheet, header_row, table_id,
     upload_id, filename, uploaded_at, key, label) = row  # fmt: skip

    headers = cur.execute(
        "SELECT col_index, header FROM source_columns WHERE table_id = ? AND col_index IN "
        "(SELECT unnest(?::INTEGER[]))",
        [table_id, list(src_cols)],
    ).fetchall()
    raw_row = cur.execute(
        "SELECT cells FROM raw_rows WHERE table_id = ? AND row_index = ?", [table_id, row_index]
    ).fetchone()
    transforms = cur.execute(
        "SELECT kind, before_value, after_value, confidence, detail, undone_in_version "
        "FROM transformations WHERE record_id = ? AND (field_id = ? OR field_id IS NULL) "
        "ORDER BY id",
        [record_id, field_id],
    ).fetchall()

    value: Any = day.isoformat() if day else (format_decimal(num) if num is not None else text)
    return {
        "record_id": record_id,
        "field": {"id": field_id, "key": key, "label": label},
        "value": value,
        "original": raw,
        "source": {
            "upload_id": upload_id,
            "filename": filename,
            "uploaded_at": uploaded_at.isoformat(),
            "sheet": sheet,
            "row": row_index,
            "header_row": header_row,
            "columns": [{"index": c, "header": h} for c, h in headers],
            "raw_row": list(raw_row[0]) if raw_row else [],
        },
        "record_status": status,
        "duplicate_of": dup_of,
        "transforms": [
            {
                "kind": k,
                "before": b,
                "after": a,
                "confidence": conf,
                "detail": json.loads(d) if isinstance(d, str) else d,
                "undone": undone is not None,
            }
            for k, b, a, conf, d, undone in transforms
        ],
    }


def get_upload(cur: Cursor, upload_id: int) -> dict[str, Any] | None:
    row = cur.execute(
        "SELECT id, workspace_id, version_id, filename, size_bytes, status, error_code, "
        "created_at FROM uploads WHERE id = ?",
        [upload_id],
    ).fetchone()
    if row is None:
        return None
    tables = cur.execute(
        "SELECT id, sheet, header_row, dataset_id FROM upload_tables WHERE upload_id = ? "
        "ORDER BY id",
        [upload_id],
    ).fetchall()
    out_tables = []
    for table_id, sheet, header_row, dataset_id in tables:
        columns = cur.execute(
            "SELECT col_index, header, role, confidence, engine, reasons, field_id "
            "FROM source_columns WHERE table_id = ? ORDER BY col_index",
            [table_id],
        ).fetchall()
        counts = cur.execute(
            "SELECT kind, count(*) FROM transformations WHERE table_id = ? GROUP BY kind",
            [table_id],
        ).fetchall()
        out_tables.append(
            {
                "id": table_id,
                "sheet": sheet,
                "header_row": header_row,
                "dataset_id": dataset_id,
                "columns": [
                    {
                        "col_index": c[0],
                        "header": c[1],
                        "role": c[2],
                        "confidence": c[3],
                        "engine": c[4],
                        "reasons": json.loads(c[5]) if isinstance(c[5], str) else c[5],
                        "field_id": c[6],
                    }
                    for c in columns
                ],
                "transforms": dict(counts),
            }
        )
    return {
        "id": row[0],
        "workspace_id": row[1],
        "version_id": row[2],
        "filename": row[3],
        "size_bytes": row[4],
        "status": row[5],
        "error_code": row[6],
        "created_at": row[7].isoformat(),
        "tables": out_tables,
    }
