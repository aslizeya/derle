"""Version timeline and point-in-time restore.

Restoring to version *v* is itself a new version R (nothing is rewritten or deleted):

* records and cells that are current now but were not valid at *v* are closed at R
* rows that were valid at *v* but are not current now are re-opened as copies from R
* human decisions are brought back to their state at *v* (revoked or re-issued at R)
* entity membership is not copied: it is *derived*, so resolution simply re-runs

Afterwards "restore to version R-1" undoes the restore, the same way.
"""

from __future__ import annotations

import json
from typing import Any

from derle.services.entities import resolve_workspace
from derle.storage import repo
from derle.storage.repo import Cursor


class HistoryError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _valid_at(alias: str, version: str) -> str:
    return (
        f"{alias}.version_from <= {version} "
        f"AND ({alias}.version_to IS NULL OR {alias}.version_to > {version})"
    )


def list_versions(cur: Cursor, workspace_id: int, *, limit: int = 200) -> list[dict[str, Any]]:
    rows = cur.execute(
        """
        SELECT v.id, v.kind, v.message, v.details, v.created_at,
          (SELECT count(*) FROM records r JOIN datasets d ON d.id = r.dataset_id
            WHERE d.workspace_id = v.workspace_id AND r.version_from = v.id
              AND r.status = 'active') AS added,
          (SELECT count(*) FROM records r JOIN datasets d ON d.id = r.dataset_id
            WHERE d.workspace_id = v.workspace_id AND r.version_to = v.id
              AND r.status = 'active') AS removed,
          (SELECT count(*) FROM cells c JOIN records r ON r.id = c.record_id
            AND r.version_from < v.id AND (r.version_to IS NULL OR r.version_to >= v.id)
            JOIN datasets d ON d.id = r.dataset_id
            WHERE d.workspace_id = v.workspace_id AND c.version_from = v.id) AS changed
        FROM versions v
        WHERE v.workspace_id = ?
        ORDER BY v.id DESC
        LIMIT ?
        """,
        [workspace_id, limit],
    ).fetchall()
    current = rows[0][0] if rows else None
    out = []
    for vid, kind, message, details, created, added, removed, changed in rows:
        out.append(
            {
                "id": vid,
                "kind": kind,
                "message": message,
                "details": json.loads(details) if isinstance(details, str) else (details or {}),
                "created_at": created.isoformat(),
                "added": int(added),
                "removed": int(removed),
                "changed": int(changed),
                "is_current": vid == current,
            }
        )
    return out


def restore(cur: Cursor, workspace_id: int, target: int) -> int:
    row = cur.execute(
        "SELECT id FROM versions WHERE id = ? AND workspace_id = ?", [target, workspace_id]
    ).fetchone()
    if row is None:
        raise HistoryError("version_not_found")
    latest = cur.execute(
        "SELECT max(id) FROM versions WHERE workspace_id = ?", [workspace_id]
    ).fetchone()
    if latest is not None and latest[0] == target:
        raise HistoryError("already_current")

    version_id = repo.create_version(
        cur, workspace_id, "restore", f"restore to version {target}", {"to": target}
    )
    ws_records = (
        "SELECT r2.id FROM records r2 JOIN datasets d ON d.id = r2.dataset_id "
        "WHERE d.workspace_id = ?"
    )

    # Records: re-open what was valid at the target, close what was not.
    reopen = cur.execute(
        f"""
        SELECT r.id, r.dataset_id, r.table_id, r.row_index, r.status, r.duplicate_of
        FROM records r JOIN datasets d ON d.id = r.dataset_id
        WHERE d.workspace_id = ? AND {_valid_at("r", "?")}
          AND NOT EXISTS (
            SELECT 1 FROM records cur WHERE cur.id = r.id AND cur.version_to IS NULL
              AND cur.version_from = r.version_from)
        """,
        [workspace_id, target, target],
    ).fetchall()
    reopen_ids = [int(r[0]) for r in reopen]
    cur.execute(
        f"""
        UPDATE records SET version_to = ?
        WHERE version_to IS NULL AND id IN ({ws_records})
          AND (version_from > ? OR id IN (SELECT unnest(?::BIGINT[])))
        """,
        [version_id, workspace_id, target, reopen_ids],
    )
    for rid, dataset_id, table_id, row_index, status, dup in reopen:
        cur.execute(
            "INSERT INTO records (id, dataset_id, table_id, row_index, status, duplicate_of, "
            "version_from) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [rid, dataset_id, table_id, row_index, status, dup, version_id],
        )

    # Cells: same rule, keyed by (record, field).
    cell_reopen = cur.execute(
        f"""
        SELECT c.record_id, c.field_id, c.value_text, c.value_num, c.value_date, c.raw_value,
               c.src_cols
        FROM cells c
        WHERE c.record_id IN ({ws_records}) AND {_valid_at("c", "?")}
          AND NOT EXISTS (
            SELECT 1 FROM cells cur WHERE cur.record_id = c.record_id
              AND cur.field_id = c.field_id AND cur.version_to IS NULL
              AND cur.version_from = c.version_from)
        """,
        [workspace_id, target, target],
    ).fetchall()
    keys = [f"{int(r[0])}:{int(r[1])}" for r in cell_reopen]
    cur.execute(
        f"""
        UPDATE cells SET version_to = ?
        WHERE version_to IS NULL AND record_id IN ({ws_records})
          AND (version_from > ?
               OR record_id::VARCHAR || ':' || field_id::VARCHAR
                  IN (SELECT unnest(?::VARCHAR[])))
        """,
        [version_id, workspace_id, target, keys],
    )
    for record_id, field_id, text, num, day, raw, src in cell_reopen:
        cur.execute(
            "INSERT INTO cells (record_id, field_id, value_text, value_num, value_date, "
            "raw_value, src_cols, version_from) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [record_id, field_id, text, num, day, raw, src, version_id],
        )

    # Transformations: undo marks made after the target no longer apply.
    cur.execute(
        """
        UPDATE transformations SET undone_in_version = NULL
        WHERE undone_in_version > ? AND table_id IN (
            SELECT t.id FROM upload_tables t JOIN uploads u ON u.id = t.upload_id
            WHERE u.workspace_id = ?)
        """,
        [target, workspace_id],
    )

    # Decisions: active-at-target is the goal state.
    cur.execute(
        "UPDATE match_decisions SET revoked_version = ? "
        "WHERE workspace_id = ? AND revoked_version IS NULL AND version_id > ?",
        [version_id, workspace_id, target],
    )
    revived = cur.execute(
        """
        SELECT candidate_id, profile_a, profile_b, decision FROM match_decisions
        WHERE workspace_id = ? AND version_id <= ? AND revoked_version > ?
        """,
        [workspace_id, target, target],
    ).fetchall()
    for candidate_id, a, b, decision in revived:
        cur.execute(
            "INSERT INTO match_decisions (workspace_id, candidate_id, profile_a, profile_b, "
            "decision, version_id) VALUES (?, ?, ?, ?, ?, ?)",
            [workspace_id, candidate_id, a, b, decision, version_id],
        )
    _sync_candidate_status(cur, workspace_id)
    _sync_upload_status(cur, workspace_id)

    for (dataset_id,) in cur.execute(
        "SELECT id FROM datasets WHERE workspace_id = ?", [workspace_id]
    ).fetchall():
        repo.rebuild_dataset_view(cur, int(dataset_id))
    resolve_workspace(cur, workspace_id, version_id)
    return version_id


def _sync_candidate_status(cur: Cursor, workspace_id: int) -> None:
    status = {"same": "accepted", "different": "rejected", "skip": "skipped"}
    active = dict(
        cur.execute(
            "SELECT candidate_id, decision FROM match_decisions "
            "WHERE workspace_id = ? AND revoked_version IS NULL AND candidate_id IS NOT NULL",
            [workspace_id],
        ).fetchall()
    )
    for cid, current in cur.execute(
        "SELECT id, status FROM match_candidates WHERE workspace_id = ?", [workspace_id]
    ).fetchall():
        wanted = (
            status[active[cid]]
            if cid in active
            else ("pending" if current in status.values() else current)
        )
        if wanted != current:
            cur.execute("UPDATE match_candidates SET status = ? WHERE id = ?", [wanted, cid])


def _sync_upload_status(cur: Cursor, workspace_id: int) -> None:
    cur.execute(
        """
        UPDATE uploads u SET status = CASE WHEN EXISTS (
            SELECT 1 FROM records r JOIN upload_tables t ON t.id = r.table_id
            WHERE t.upload_id = u.id AND r.version_to IS NULL) THEN 'done' ELSE 'undone' END
        WHERE u.workspace_id = ? AND u.status IN ('done', 'undone')
        """,
        [workspace_id],
    )
