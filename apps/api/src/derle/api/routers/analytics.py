from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field

from derle.analytics.dashboard import build_dashboard
from derle.analytics.quality import quality_report
from derle.analytics.schema import load_schema
from derle.api.deps import DbDep, LlmDep
from derle.api.errors import from_code, not_found
from derle.nlq.service import ask, recent_questions
from derle.services import export, history

router = APIRouter(tags=["analytics"])


# --- models -------------------------------------------------------------------------------


class QualityIssue(BaseModel):
    code: str
    count: int
    penalty: float
    severity: Literal["serious", "warning", "info"]
    params: dict[str, Any]
    action: dict[str, Any]


class FieldCompleteness(BaseModel):
    key: str
    label: str
    role: str
    filled: int
    ratio: float


class QualityNote(BaseModel):
    code: str
    count: int


class QualityReport(BaseModel):
    dataset_id: int
    score: int | None
    grade: Literal["excellent", "good", "fair", "poor"] | None
    rows: int
    issues: list[QualityIssue]
    fields: list[FieldCompleteness]
    notes: list[QualityNote]


class Kpi(BaseModel):
    key: str
    value: Any
    format: Literal["count", "money", "date_range"]
    sql: str


class Chart(BaseModel):
    key: str
    kind: Literal["column", "bar"]
    x: str
    series: list[str]
    rows: list[dict[str, Any]]
    sql: str


class Dashboard(BaseModel):
    dataset_id: int
    name: str
    detected: dict[str, bool]
    kpis: list[Kpi]
    charts: list[Chart]


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=300)
    dataset_id: int | None = None


class Answer(BaseModel):
    question: str
    dataset_id: int | None
    engine: Literal["rules", "llm", "none"]
    sql: str | None
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    chart: Literal["kpi", "bar", "column", "table"]
    explanation: dict[str, Any] | None
    llm_explanation: str | None
    anchor: dict[str, str] | None
    error: str | None
    error_params: dict[str, Any] = {}
    duration_ms: int


class RecentQuestion(BaseModel):
    question: str
    asked_at: str
    ok: bool


class VersionItem(BaseModel):
    id: int
    kind: str
    message: str | None
    details: dict[str, Any]
    created_at: str
    added: int
    removed: int
    changed: int
    is_current: bool


class RestoreOut(BaseModel):
    version_id: int


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


# --- routes -------------------------------------------------------------------------------


@router.get("/datasets/{dataset_id}/quality")
def get_quality(dataset_id: int, db: DbDep) -> QualityReport:
    with db.read() as cur:
        schema = load_schema(cur, dataset_id)
        if schema is None:
            raise not_found("dataset_not_found")
        report = quality_report(cur, schema)
    return QualityReport(dataset_id=dataset_id, **report)


@router.get("/datasets/{dataset_id}/dashboard")
def get_dashboard(dataset_id: int, db: DbDep) -> Dashboard:
    with db.read() as cur:
        schema = load_schema(cur, dataset_id)
    if schema is None:
        raise not_found("dataset_not_found")
    return Dashboard(**build_dashboard(db, schema))


@router.patch("/datasets/{dataset_id}")
def rename_dataset(dataset_id: int, body: RenameIn, db: DbDep) -> dict[str, Any]:
    with db.transaction() as cur:
        row = cur.execute(
            "UPDATE datasets SET name = ? WHERE id = ? RETURNING id, name",
            [body.name.strip(), dataset_id],
        ).fetchone()
    if row is None:
        raise not_found("dataset_not_found")
    return {"id": row[0], "name": row[1]}


@router.get("/datasets/{dataset_id}/export", response_class=Response)
def export_dataset(
    dataset_id: int,
    db: DbDep,
    file_format: Annotated[Literal["xlsx", "csv"], Query(alias="format")] = "xlsx",
    mask: bool = False,
) -> Response:
    with db.read() as cur:
        schema = load_schema(cur, dataset_id)
        if schema is None:
            raise not_found("dataset_not_found")
        headers, rows, roles = export.export_rows(cur, schema, mask=mask)
    if file_format == "csv":
        content, media = export.to_csv(headers, rows), "text/csv; charset=utf-8"
    else:
        content = export.to_xlsx(schema, headers, rows, roles)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    filename = f"{schema.name}.{file_format}"
    return Response(
        content,
        media_type=media,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/workspaces/{workspace_id}/ask")
async def ask_question(workspace_id: int, body: AskIn, db: DbDep, llm: LlmDep) -> Answer:
    result = await asyncio.to_thread(
        ask, db, llm, workspace_id=workspace_id, question=body.question, dataset_id=body.dataset_id
    )
    return Answer(**result)


@router.get("/workspaces/{workspace_id}/questions")
def list_questions(workspace_id: int, db: DbDep) -> list[RecentQuestion]:
    with db.read() as cur:
        return [RecentQuestion(**q) for q in recent_questions(cur, workspace_id)]


@router.get("/workspaces/{workspace_id}/versions")
def list_versions(workspace_id: int, db: DbDep) -> list[VersionItem]:
    with db.read() as cur:
        return [VersionItem(**v) for v in history.list_versions(cur, workspace_id)]


@router.post("/workspaces/{workspace_id}/versions/{version_id}/restore")
def restore_version(workspace_id: int, version_id: int, db: DbDep) -> RestoreOut:
    try:
        with db.transaction() as cur:
            return RestoreOut(version_id=history.restore(cur, workspace_id, version_id))
    except history.HistoryError as exc:
        raise from_code(exc.code) from exc
