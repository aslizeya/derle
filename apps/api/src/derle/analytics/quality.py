"""Data quality report: a 0–100 score plus concrete "fix this" suggestions.

The score is deliberately simple and explainable: it starts at 100 and every issue
subtracts a capped, documented penalty. Each issue carries a code, a count and an action
target, so the UI can say *what* is wrong and link straight to where to fix it.

| Issue               | What it means                                         | Max penalty |
|---------------------|-------------------------------------------------------|-------------|
| missing_values      | a key field (customer, date, money) is empty          | 35          |
| unreadable_values   | a date/number cell kept as raw text                   | 25          |
| pending_matches     | customers that may be the same are still unconfirmed  | 15          |
| uncertain_values    | guessed year, ambiguous day/month or decimal mark      | 10          |
| outliers            | money far outside the usual range (robust MAD rule)   | 10          |
| future_dates        | dates after today                                     | 5           |
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import date
from typing import Any

from derle.analytics.schema import DatasetSchema
from derle.storage.repo import Cursor

PENALTY_CAPS = {
    "missing_values": 35.0,
    "unreadable_values": 25.0,
    "pending_matches": 15.0,
    "uncertain_values": 10.0,
    "outliers": 10.0,
    "future_dates": 5.0,
}
# Money is roughly log-normal (many small sales, few large ones), so the robust rule runs on
# log values: flagged amounts are more than ~e^4 ≈ 55× the typical spread from the median.
OUTLIER_LOG_MADS = 4.0
GRADES = ((90, "excellent"), (75, "good"), (50, "fair"), (0, "poor"))


def _issue(
    code: str,
    count: int,
    penalty: float,
    severity: str,
    action: dict[str, Any],
    **params: Any,
) -> dict[str, Any]:
    return {
        "code": code,
        "count": count,
        "penalty": round(min(penalty, PENALTY_CAPS[code]), 1),
        "severity": severity,
        "params": params,
        "action": action,
    }


def _count(cur: Cursor, sql: str, params: list[Any] | None = None) -> int:
    row = cur.execute(sql, params or []).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _completeness(cur: Cursor, schema: DatasetSchema, rows: int) -> list[dict[str, Any]]:
    fields = []
    for col in schema.columns:
        filled = _count(cur, f"SELECT count({schema.q(col)}) FROM {schema.view}")
        fields.append(
            {
                "key": col.key,
                "label": col.label,
                "role": col.role,
                "filled": filled,
                "ratio": round(filled / rows, 4),
            }
        )
    return fields


def _missing_issues(
    cur: Cursor, schema: DatasetSchema, rows: int, fields: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Key fields: who (customer), when (date) and how much (any money column)."""
    issues = []

    def add(missing: int, field: str, role: str, action: dict[str, Any]) -> None:
        if missing:
            severity = "serious" if missing / rows > 0.1 else "warning"
            issues.append(
                _issue(
                    "missing_values",
                    missing,
                    35 * missing / rows,
                    severity,
                    action,
                    field=field,
                    role=role,
                )
            )

    for key_col in (schema.party, schema.date):
        if key_col is not None:
            filled = next(f["filled"] for f in fields if f["key"] == key_col.key)
            add(rows - filled, key_col.label, key_col.role, {"kind": "table", "sort": key_col.name})
    if schema.has_money:
        money = [c for c in schema.columns if c.role in ("debit", "credit", "amount")]
        empty = " AND ".join(f"{schema.q(c)} IS NULL" for c in money)
        add(
            _count(cur, f"SELECT count(*) FROM {schema.view} WHERE {empty}"),
            "money",
            "amount",
            {"kind": "table"},
        )
    return issues


def _log_issues(cur: Cursor, schema: DatasetSchema, rows: int) -> list[dict[str, Any]]:
    """Unreadable and uncertain values, from the transformation log of active records."""
    log = cur.execute(
        """
        SELECT t.kind, t.confidence, t.detail, ut.upload_id
        FROM transformations t
        JOIN records r ON r.id = t.record_id AND r.version_to IS NULL AND r.status = 'active'
        JOIN upload_tables ut ON ut.id = t.table_id
        WHERE r.dataset_id = ? AND t.undone_in_version IS NULL
        """,
        [schema.dataset_id],
    ).fetchall()
    issues = []
    unreadable = [r for r in log if r[0] == "parse_failed"]
    if unreadable:
        action = {"kind": "review", "upload_id": int(unreadable[0][3]), "filter": "parse_failed"}
        issues.append(
            _issue(
                "unreadable_values",
                len(unreadable),
                100 * len(unreadable) / rows,
                "serious",
                action,
            )
        )
    uncertain = {"year_inferred": 0, "ambiguous_order": 0, "ambiguous_number": 0}
    by_upload: dict[int, int] = {}
    for kind, confidence, detail, upload_id in log:
        if kind == "parse_failed" or confidence >= 1:
            continue
        by_upload[int(upload_id)] = by_upload.get(int(upload_id), 0) + 1
        d = json.loads(detail) if isinstance(detail, str) else detail
        if d.get("year_inferred"):
            uncertain["year_inferred"] += 1
        elif d.get("ambiguous_order"):
            uncertain["ambiguous_order"] += 1
        elif d.get("ambiguous"):
            uncertain["ambiguous_number"] += 1
    total = sum(uncertain.values())
    if total:
        issues.append(
            _issue(
                "uncertain_values",
                total,
                10 * total / rows,
                "info",
                {"kind": "review", "upload_id": max(by_upload, key=lambda u: by_upload[u])},
                **uncertain,
            )
        )
    return issues


def _pending_matches(cur: Cursor, schema: DatasetSchema) -> list[dict[str, Any]]:
    """Customers that might be the same person, still waiting for a decision."""
    pending = _count(
        cur,
        """
        SELECT count(DISTINCT c.id) FROM match_candidates c
        WHERE c.workspace_id = ? AND c.status = 'pending' AND EXISTS (
            SELECT 1 FROM entity_members em JOIN records r ON r.id = em.record_id
            WHERE em.version_to IS NULL AND r.version_to IS NULL AND r.dataset_id = ?
              AND em.entity_id IN (c.entity_a, c.entity_b))
        """,
        [schema.workspace_id, schema.dataset_id],
    )
    if not pending:
        return []
    return [_issue("pending_matches", pending, pending, "warning", {"kind": "matching"})]


def _outliers(cur: Cursor, schema: DatasetSchema) -> list[dict[str, Any]]:
    issues = []
    for col in schema.columns:
        if col.role not in ("debit", "credit", "amount"):
            continue
        values = [
            float(v[0])
            for v in cur.execute(
                f"SELECT abs({schema.q(col)}) FROM {schema.view} "
                f"WHERE {schema.q(col)} IS NOT NULL AND {schema.q(col)} <> 0"
            ).fetchall()
        ]
        if len(values) < 10:
            continue
        logs = [math.log(v) for v in values]
        median = statistics.median(logs)
        mad = statistics.median(abs(x - median) for x in logs) or 0.1
        limit = math.exp(median + OUTLIER_LOG_MADS * mad)
        outliers = sorted((v for v in values if v > limit), reverse=True)
        if outliers:
            issues.append(
                _issue(
                    "outliers",
                    len(outliers),
                    2 * len(outliers),
                    "info",
                    {"kind": "table", "sort": col.name, "desc": True},
                    field=col.label,
                    threshold=round(limit, 2),
                    examples=[round(v, 2) for v in outliers[:3]],
                )
            )
    return issues


def _future_dates(cur: Cursor, schema: DatasetSchema, today: date) -> list[dict[str, Any]]:
    if schema.date is None:
        return []
    future = _count(
        cur, f"SELECT count(*) FROM {schema.view} WHERE {schema.q(schema.date)} > ?", [today]
    )
    if not future:
        return []
    action = {"kind": "table", "sort": schema.date.name, "desc": True}
    return [_issue("future_dates", future, future, "warning", action, today=today.isoformat())]


def quality_report(
    cur: Cursor, schema: DatasetSchema, *, today: date | None = None
) -> dict[str, Any]:
    today = today or date.today()
    rows = _count(cur, f"SELECT count(*) FROM {schema.view}")
    if rows == 0:
        return {"score": None, "grade": None, "rows": 0, "issues": [], "fields": [], "notes": []}

    fields = _completeness(cur, schema, rows)
    issues = [
        *_missing_issues(cur, schema, rows, fields),
        *_log_issues(cur, schema, rows),
        *_pending_matches(cur, schema),
        *_outliers(cur, schema),
        *_future_dates(cur, schema, today),
    ]
    score = max(0, round(100 - sum(i["penalty"] for i in issues)))
    grade = next(g for threshold, g in GRADES if score >= threshold)

    notes = []
    duplicates = _count(
        cur,
        "SELECT count(*) FROM records WHERE dataset_id = ? AND version_to IS NULL "
        "AND status = 'duplicate'",
        [schema.dataset_id],
    )
    if duplicates:
        notes.append({"code": "duplicates_removed", "count": duplicates})

    order = {"serious": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: (order[i["severity"]], -i["penalty"]))
    return {
        "score": score,
        "grade": grade,
        "rows": rows,
        "issues": issues,
        "fields": fields,
        "notes": notes,
    }
