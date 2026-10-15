from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from derle.api.deps import DbDep
from derle.api.errors import not_found
from derle.api.schemas import CellMark, DatasetOut, DatasetSummary, ProvenanceOut, RecordsPage
from derle.services import queries

router = APIRouter(tags=["datasets"])


@router.get("/workspaces/{workspace_id}/datasets")
def list_datasets(workspace_id: int, db: DbDep) -> list[DatasetSummary]:
    with db.read() as cur:
        return [DatasetSummary(**d) for d in queries.list_datasets(cur, workspace_id)]


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: int, db: DbDep) -> DatasetOut:
    with db.read() as cur:
        dataset = queries.get_dataset(cur, dataset_id)
    if dataset is None:
        raise not_found("dataset_not_found")
    return DatasetOut(**dataset)


@router.get("/datasets/{dataset_id}/records")
def list_records(
    dataset_id: int,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: Annotated[str | None, Query(max_length=100)] = None,
    desc: bool = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> RecordsPage:
    with db.read() as cur:
        if queries.get_dataset(cur, dataset_id) is None:
            raise not_found("dataset_not_found")
        rows, total = queries.list_records(
            cur, dataset_id, limit=limit, offset=offset, sort=sort, descending=desc, query=q
        )
        marks = queries.cell_marks(cur, [int(r["record_id"]) for r in rows])
    return RecordsPage(
        total=total,
        limit=limit,
        offset=offset,
        rows=rows,
        marks={
            str(rid): {col: CellMark(**m) for col, m in cols.items()} for rid, cols in marks.items()
        },
    )


@router.get("/records/{record_id}/cells/{field_id}/provenance")
def cell_provenance(record_id: int, field_id: int, db: DbDep) -> ProvenanceOut:
    with db.read() as cur:
        result = queries.cell_provenance(cur, record_id, field_id)
    if result is None:
        raise not_found("cell_not_found")
    return ProvenanceOut(**result)
