"""Before/after review of an upload and undo of individual transformations or whole uploads.

Undo never deletes. It opens a new version, closes the affected rows (``version_to``) and
inserts their replacements, then re-runs entity resolution, because a restored duplicate or
an un-normalized name can change who matches whom.
"""

from __future__ import annotations

import json
from typing import Any

from derle.services.entities import resolve_workspace
from derle.storage import repo
from derle.storage.repo import Cursor

NOT_UNDOABLE = frozenset({"parse_failed"})


class ReviewError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _value(text: str | None, num: Any, day: Any) -> Any:
    if day is not None:
        return day.isoformat()
    if num is not None:
        return float(num)
    return text


def _detail(raw: Any) -> Any:
    return json.loads(raw) if isinstance(raw, str) else raw


def table_diff(cur: Cursor, table_id: int, *, offset: int, limit: int) -> dict[str, Any] | None:
    meta = cur.execute(
        "SELECT t.id, t.upload_id, t.sheet, t.header_row, t.dataset_id, u.filename "
        "FROM upload_tables t JOIN uploads u ON u.id = t.upload_id WHERE t.id = ?",
        [table_id],
    ).fetchone()
    if meta is None:
        return None
    _, upload_id, sheet, header_row, dataset_id, filename = meta

    columns = [
        {"col_index": c, "header": h, "role": r, "confidence": conf, "field_id": fid}
        for c, h, r, conf, fid in cur.execute(
            "SELECT col_index, header, role, confidence, field_id FROM source_columns "
            "WHERE table_id = ? ORDER BY col_index",
            [table_id],
        ).fetchall()
    ]
    field_ids = list(dict.fromkeys(c["field_id"] for c in columns if c["field_id"] is not None))
    fields_by_id = {int(f["id"]): f for f in repo.get_fields(cur, dataset_id)}
    fields = [fields_by_id[fid] for fid in field_ids if fid in fields_by_id]
    for f in fields:
        f["column"] = repo.column_name(f["key"])

    total_row = cur.execute(
        "SELECT count(*) FROM raw_rows WHERE table_id = ?", [table_id]
    ).fetchone()
    raw = cur.execute(
        "SELECT row_index, cells, skip_reason FROM raw_rows WHERE table_id = ? "
        "ORDER BY row_index LIMIT ? OFFSET ?",
        [table_id, limit, offset],
    ).fetchall()
    indexes = [int(r[0]) for r in raw]

    records = {
        int(ri): {"id": int(rid), "status": st, "duplicate_of": dup, "values": {}, "transforms": {}}
        for rid, ri, st, dup in cur.execute(
            "SELECT id, row_index, status, duplicate_of FROM records WHERE table_id = ? "
            "AND version_to IS NULL AND row_index IN (SELECT unnest(?::INTEGER[]))",
            [table_id, indexes],
        ).fetchall()
    }
    by_record = {r["id"]: r for r in records.values()}
    record_ids = list(by_record)
    key_of = {int(f["id"]): f["key"] for f in fields}

    for rid, fid, text, num, day in cur.execute(
        "SELECT record_id, field_id, value_text, value_num, value_date FROM cells "
        "WHERE version_to IS NULL AND record_id IN (SELECT unnest(?::BIGINT[]))",
        [record_ids],
    ).fetchall():
        if fid in key_of:
            by_record[int(rid)]["values"][key_of[fid]] = _value(text, num, day)

    row_transforms: dict[int, list[dict[str, Any]]] = {}
    for tid, rid, fid, kind, before, after, conf, detail, undone in cur.execute(
        "SELECT id, record_id, field_id, kind, before_value, after_value, confidence, detail, "
        "undone_in_version FROM transformations "
        "WHERE table_id = ? AND record_id IN (SELECT unnest(?::BIGINT[])) ORDER BY id",
        [table_id, record_ids],
    ).fetchall():
        item = {
            "id": tid,
            "kind": kind,
            "before": before,
            "after": after,
            "confidence": conf,
            "detail": _detail(detail),
            "undone": undone is not None,
        }
        if fid is None:
            row_transforms.setdefault(int(rid), []).append(item)
        elif fid in key_of:
            by_record[int(rid)]["transforms"].setdefault(key_of[fid], []).append(item)

    rows = []
    for row_index, cells, skip in raw:
        record = records.get(int(row_index))
        if record is not None:
            record["row_transforms"] = row_transforms.get(record["id"], [])
        rows.append(
            {
                "row_index": int(row_index),
                "raw": [c if c != "" else None for c in cells],
                "skip_reason": skip,
                "record": record,
            }
        )

    return {
        "table_id": table_id,
        "upload_id": upload_id,
        "filename": filename,
        "sheet": sheet,
        "header_row": header_row,
        "dataset_id": dataset_id,
        "columns": columns,
        "fields": fields,
        "total_rows": int(total_row[0]) if total_row else 0,
        "offset": offset,
        "rows": rows,
    }


def transformation_summary(cur: Cursor, table_id: int) -> list[dict[str, Any]]:
    return [
        {"kind": k, "count": int(n), "undone": int(u)}
        for k, n, u in cur.execute(
            "SELECT kind, count(*), count(undone_in_version) FROM transformations "
            "WHERE table_id = ? GROUP BY kind ORDER BY count(*) DESC, kind",
            [table_id],
        ).fetchall()
    ]


def list_transformations(
    cur: Cursor, table_id: int, *, kind: str | None, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    where = "t.table_id = ?"
    params: list[Any] = [table_id]
    if kind:
        where += " AND t.kind = ?"
        params.append(kind)
    total = cur.execute(f"SELECT count(*) FROM transformations t WHERE {where}", params).fetchone()
    rows = cur.execute(
        f"""
        SELECT t.id, t.kind, t.before_value, t.after_value, t.confidence, t.detail,
               t.undone_in_version, t.record_id, r.row_index, f.key, f.label
        FROM transformations t
        LEFT JOIN (SELECT DISTINCT id, row_index FROM records) r ON r.id = t.record_id
        LEFT JOIN fields f ON f.id = t.field_id
        WHERE {where}
        ORDER BY r.row_index, t.id
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    return (
        [
            {
                "id": tid,
                "kind": k,
                "before": b,
                "after": a,
                "confidence": c,
                "detail": _detail(d),
                "undone": u is not None,
                "record_id": rid,
                "row_index": ri,
                "field_key": fk,
                "field_label": fl,
            }
            for tid, k, b, a, c, d, u, rid, ri, fk, fl in rows
        ],
        int(total[0]) if total else 0,
    )


def _workspace_of_table(cur: Cursor, table_id: int) -> tuple[int, int]:
    row = cur.execute(
        "SELECT u.workspace_id, t.dataset_id FROM upload_tables t "
        "JOIN uploads u ON u.id = t.upload_id WHERE t.id = ?",
        [table_id],
    ).fetchone()
    if row is None:
        raise ReviewError("table_not_found")
    return int(row[0]), int(row[1])


def undo_transformation(cur: Cursor, transformation_id: int) -> int:
    """Revert one change. Field-level changes put the original text back into the cell
    (all transformations on that cell are undone together, since they produced one value).
    ``duplicate_removed`` brings the row back as an active record."""
    row = cur.execute(
        "SELECT table_id, record_id, field_id, kind, undone_in_version FROM transformations "
        "WHERE id = ?",
        [transformation_id],
    ).fetchone()
    if row is None:
        raise ReviewError("transformation_not_found")
    table_id, record_id, field_id, kind, undone = row
    if undone is not None:
        raise ReviewError("already_undone")
    if kind in NOT_UNDOABLE:
        raise ReviewError("not_undoable")
    workspace_id, dataset_id = _workspace_of_table(cur, table_id)
    version_id = repo.create_version(
        cur,
        workspace_id,
        "undo",
        f"undo {kind} #{transformation_id}",
        {"target": "transformation", "kind": kind},
    )

    if field_id is None:  # row-level: duplicate_removed
        _reopen_record(cur, record_id, version_id, status="active")
        cur.execute(
            "UPDATE transformations SET undone_in_version = ? WHERE id = ?",
            [version_id, transformation_id],
        )
    else:
        cell = cur.execute(
            "SELECT raw_value, src_cols FROM cells WHERE record_id = ? AND field_id = ? "
            "AND version_to IS NULL",
            [record_id, field_id],
        ).fetchone()
        if cell is None:
            raise ReviewError("cell_not_found")
        cur.execute(
            "UPDATE cells SET version_to = ? WHERE record_id = ? AND field_id = ? "
            "AND version_to IS NULL",
            [version_id, record_id, field_id],
        )
        cur.execute(
            "INSERT INTO cells (record_id, field_id, value_text, raw_value, src_cols, "
            "version_from) VALUES (?, ?, ?, ?, ?, ?)",
            [record_id, field_id, cell[0], cell[0], cell[1], version_id],
        )
        cur.execute(
            "UPDATE transformations SET undone_in_version = ? WHERE record_id = ? "
            "AND field_id = ? AND undone_in_version IS NULL",
            [version_id, record_id, field_id],
        )

    repo.rebuild_dataset_view(cur, dataset_id)
    resolve_workspace(cur, workspace_id, version_id)
    return version_id


def _reopen_record(cur: Cursor, record_id: int, version_id: int, *, status: str) -> None:
    current = cur.execute(
        "SELECT dataset_id, table_id, row_index FROM records WHERE id = ? AND version_to IS NULL",
        [record_id],
    ).fetchone()
    if current is None:
        raise ReviewError("record_not_found")
    cur.execute(
        "UPDATE records SET version_to = ? WHERE id = ? AND version_to IS NULL",
        [version_id, record_id],
    )
    cur.execute(
        "INSERT INTO records (id, dataset_id, table_id, row_index, status, version_from) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [record_id, *current, status, version_id],
    )


def undo_upload(cur: Cursor, upload_id: int) -> int:
    """Take a whole upload out of the clean data. Its raw rows stay for the record."""
    row = cur.execute(
        "SELECT workspace_id, status, filename FROM uploads WHERE id = ?", [upload_id]
    ).fetchone()
    if row is None:
        raise ReviewError("upload_not_found")
    workspace_id, status, filename = row
    if status != "done":
        raise ReviewError("upload_not_active")
    version_id = repo.create_version(
        cur,
        workspace_id,
        "undo",
        f"undo upload {filename}",
        {"target": "upload", "filename": filename},
    )
    tables = [
        (int(t), int(d))
        for t, d in cur.execute(
            "SELECT id, dataset_id FROM upload_tables WHERE upload_id = ?", [upload_id]
        ).fetchall()
    ]
    table_ids = [t for t, _ in tables]
    cur.execute(
        "UPDATE cells SET version_to = ? WHERE version_to IS NULL AND record_id IN "
        "(SELECT id FROM records WHERE version_to IS NULL "
        " AND table_id IN (SELECT unnest(?::BIGINT[])))",
        [version_id, table_ids],
    )
    cur.execute(
        "UPDATE records SET version_to = ? WHERE version_to IS NULL "
        "AND table_id IN (SELECT unnest(?::BIGINT[]))",
        [version_id, table_ids],
    )
    cur.execute("UPDATE uploads SET status = 'undone' WHERE id = ?", [upload_id])
    for dataset_id in {d for _, d in tables}:
        repo.rebuild_dataset_view(cur, dataset_id)
    resolve_workspace(cur, workspace_id, version_id)
    return version_id


__all__ = [
    "ReviewError",
    "list_transformations",
    "table_diff",
    "transformation_summary",
    "undo_transformation",
    "undo_upload",
]
