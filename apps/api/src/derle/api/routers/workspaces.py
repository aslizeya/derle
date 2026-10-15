from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from derle.api.deps import DbDep, LlmDep
from derle.api.errors import not_found
from derle.api.schemas import WorkspaceOut, WorkspaceSummary
from derle.services import queries
from derle.storage import repo

router = APIRouter(tags=["workspaces"])


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.get("/health")
def health(llm: LlmDep) -> dict[str, str | bool]:
    return {"status": "ok", "ai_enabled": llm.enabled, "ai_provider": llm.name}


@router.get("/workspaces")
def list_workspaces(db: DbDep) -> list[WorkspaceOut]:
    with db.read() as cur:
        rows = cur.execute(
            "SELECT id, name, is_demo FROM workspaces WHERE NOT is_demo ORDER BY id"
        ).fetchall()
    return [WorkspaceOut(id=r[0], name=r[1], is_demo=r[2]) for r in rows]


@router.post("/workspaces", status_code=201)
def create_workspace(body: WorkspaceIn, db: DbDep) -> WorkspaceOut:
    with db.transaction() as cur:
        workspace_id = repo.insert_returning_id(
            cur, "INSERT INTO workspaces (name) VALUES (?)", [body.name]
        )
    return WorkspaceOut(id=workspace_id, name=body.name, is_demo=False)


@router.get("/workspaces/{workspace_id}")
def get_workspace(workspace_id: int, db: DbDep) -> WorkspaceSummary:
    with db.read() as cur:
        summary = queries.workspace_summary(cur, workspace_id)
    if summary is None:
        raise not_found("workspace_not_found")
    return WorkspaceSummary(**summary)
