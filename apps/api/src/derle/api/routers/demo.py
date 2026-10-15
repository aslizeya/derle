""" "Örnek veriyle dene": a throwaway workspace plus the generated six-month ledger.

The frontend downloads the sample files and uploads them through the normal upload flow,
so the demo exercises exactly the code path real users hit.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Response

from derle.api.deps import DbDep
from derle.api.errors import not_found
from derle.api.schemas import DemoFile, WorkspaceOut
from derle.demo.sample_ledger import SampleLedger, generate
from derle.storage import repo

router = APIRouter(prefix="/demo", tags=["demo"])

DEMO_SEED = 7
DEMO_NAME = "Örnek: Kardeşler Bakkaliyesi"
_MEDIA_TYPES = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@lru_cache(maxsize=1)
def _ledger() -> SampleLedger:
    return generate(DEMO_SEED)


@router.post("/workspaces", status_code=201)
def create_demo_workspace(db: DbDep) -> WorkspaceOut:
    with db.transaction() as cur:
        workspace_id = repo.insert_returning_id(
            cur, "INSERT INTO workspaces (name, is_demo) VALUES (?, TRUE)", [DEMO_NAME]
        )
    return WorkspaceOut(id=workspace_id, name=DEMO_NAME, is_demo=True)


@router.get("/files")
def list_demo_files() -> list[DemoFile]:
    return [DemoFile(name=f.name, size=len(f.data)) for f in _ledger().files]


@router.get("/files/{name}", response_class=Response)
def get_demo_file(name: str) -> Response:
    for f in _ledger().files:
        if f.name == name:
            media = _MEDIA_TYPES.get(name[name.rfind(".") :], "application/octet-stream")
            return Response(f.data, media_type=media)
    raise not_found("demo_file_not_found")
