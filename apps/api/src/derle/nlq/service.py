"""Answer a question: plan (rules, then optional LLM) → guard → run → log."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from derle.analytics.execute import QueryTimeoutError, run_select
from derle.analytics.schema import DatasetSchema, load_schema
from derle.llm.base import LLMProvider
from derle.nlq.guard import GuardError, guard_sql
from derle.nlq.llm import generate_sql
from derle.nlq.rules import (
    EntityName,
    PlanError,
    explain,
    plan_question,
    plan_to_sql,
    suggest_chart,
)
from derle.normalize.tr.text import fold
from derle.storage.db import Database
from derle.storage.repo import Cursor

MAX_ROWS = 500
# If the newest record is older than this, relative periods ("geçen ay") are anchored to the
# data instead of today, and the answer says so. Otherwise a ledger that ended in June
# would answer every "last month" question in October with nothing.
STALE_AFTER = timedelta(days=45)


def default_dataset(cur: Cursor, workspace_id: int) -> int | None:
    row = cur.execute(
        """
        SELECT d.id FROM datasets d
        LEFT JOIN records r ON r.dataset_id = d.id AND r.version_to IS NULL AND r.status = 'active'
        WHERE d.workspace_id = ?
        GROUP BY d.id ORDER BY count(r.id) DESC, d.id LIMIT 1
        """,
        [workspace_id],
    ).fetchone()
    return int(row[0]) if row else None


def anchor_date(cur: Cursor, schema: DatasetSchema, today: date) -> tuple[date, str]:
    if schema.date is None:
        return today, "today"
    row = cur.execute(f"SELECT max({schema.q(schema.date)}) FROM {schema.view}").fetchone()
    latest = row[0] if row else None
    if latest is None or latest >= today - STALE_AFTER:
        return today, "today"
    return latest, "data_end"


def entity_names(cur: Cursor, workspace_id: int) -> list[EntityName]:
    aliases: dict[int, set[str]] = defaultdict(set)
    names: dict[int, str] = {}
    for entity_id, canonical, written in cur.execute(
        """
        SELECT e.id, e.canonical_name, c.value_text
        FROM entities e
        JOIN entity_members em ON em.entity_id = e.id AND em.version_to IS NULL
        JOIN cells c ON c.record_id = em.record_id AND c.version_to IS NULL
        JOIN fields f ON f.id = c.field_id AND f.role = 'party'
        WHERE e.workspace_id = ?
        """,
        [workspace_id],
    ).fetchall():
        names[int(entity_id)] = canonical
        aliases[int(entity_id)].update({fold(canonical), fold(written or "")})
    return [
        EntityName(id=eid, name=names[eid], keys=tuple(k for k in aliases[eid] if k))
        for eid in names
    ]


def _samples(cur: Cursor, schema: DatasetSchema) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for col in schema.columns:
        if col.pii:
            continue  # never send personal data to the model
        rows = cur.execute(
            f"SELECT DISTINCT CAST({schema.q(col)} AS VARCHAR) FROM {schema.view} "
            f"WHERE {schema.q(col)} IS NOT NULL LIMIT 3"
        ).fetchall()
        out[col.name] = [r[0] for r in rows]
    return out


def ask(
    db: Database,
    llm: LLMProvider,
    *,
    workspace_id: int,
    question: str,
    dataset_id: int | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    today = today or date.today()
    response: dict[str, Any] = {
        "question": question,
        "dataset_id": dataset_id,
        "engine": "none",
        "sql": None,
        "columns": [],
        "rows": [],
        "truncated": False,
        "chart": "table",
        "explanation": None,
        "llm_explanation": None,
        "anchor": None,
        "error": None,
        "error_params": {},
    }

    with db.read() as cur:
        dataset_id = dataset_id or default_dataset(cur, workspace_id)
        schema = load_schema(cur, dataset_id) if dataset_id else None
        if schema is None or schema.workspace_id != workspace_id:
            response["error"] = "no_data"
            return _log(db, workspace_id, None, response, started)
        response["dataset_id"] = dataset_id
        anchor, anchor_reason = anchor_date(cur, schema, today)
        response["anchor"] = {"date": anchor.isoformat(), "reason": anchor_reason}
        entities = entity_names(cur, workspace_id) if schema.customer_expr else []
        try:
            plan = plan_question(question, anchor=anchor, entities=entities)
        except PlanError as exc:
            response.update(error=exc.code, error_params=exc.params)
            return _log(db, workspace_id, dataset_id, response, started)
        samples = _samples(cur, schema) if plan is None and llm.enabled else {}

    sql: str | None = None
    if plan is not None:
        try:
            sql = plan_to_sql(plan, schema)
            response.update(engine="rules", chart=suggest_chart(plan), explanation=explain(plan))
        except PlanError as exc:
            response["error"] = exc.code
            return _log(db, workspace_id, dataset_id, response, started)
    else:
        generated = generate_sql(llm, question, schema, samples, anchor)
        if generated is None:
            response["error"] = "not_understood" if not llm.enabled else "llm_no_answer"
            return _log(db, workspace_id, dataset_id, response, started)
        sql = generated.sql
        response.update(engine="llm", chart=generated.chart, llm_explanation=generated.explanation)

    try:
        safe_sql = guard_sql(sql, {schema.view}, limit=MAX_ROWS)
    except GuardError as exc:
        response.update(sql=sql, error=f"rejected_{exc.code}")
        return _log(db, workspace_id, dataset_id, response, started)
    response["sql"] = safe_sql

    try:
        columns, rows, truncated = run_select(db, safe_sql, max_rows=MAX_ROWS)
    except QueryTimeoutError:
        response["error"] = "timeout"
        return _log(db, workspace_id, dataset_id, response, started)
    except Exception:  # invalid SQL from the model: report, never crash
        response["error"] = "execution_failed"
        return _log(db, workspace_id, dataset_id, response, started)

    response.update(columns=columns, rows=rows, truncated=truncated)
    if response["chart"] == "kpi" and not (len(rows) == 1 and len(columns) == 1):
        response["chart"] = "table"
    return _log(db, workspace_id, dataset_id, response, started)


def _log(
    db: Database,
    workspace_id: int,
    dataset_id: int | None,
    response: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    duration_ms = int((time.perf_counter() - started) * 1000)
    response["duration_ms"] = duration_ms
    with db.transaction() as cur:
        cur.execute(
            "INSERT INTO query_log (workspace_id, dataset_id, question, sql, engine, ok, "
            "error_code, row_count, duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                workspace_id,
                dataset_id,
                response["question"],
                response["sql"],
                response["engine"],
                response["error"] is None,
                response["error"],
                len(response["rows"]),
                duration_ms,
            ],
        )
    return response


def recent_questions(cur: Cursor, workspace_id: int, limit: int = 10) -> list[dict[str, Any]]:
    rows = cur.execute(
        "SELECT question, max(created_at) AS last, bool_or(ok) FROM query_log "
        "WHERE workspace_id = ? GROUP BY question ORDER BY last DESC LIMIT ?",
        [workspace_id, limit],
    ).fetchall()
    return [{"question": q, "asked_at": t.isoformat(), "ok": bool(ok)} for q, t, ok in rows]
