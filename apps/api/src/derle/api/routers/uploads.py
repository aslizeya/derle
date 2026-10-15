from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from derle.api.deps import DbDep, LlmDep, SettingsDep
from derle.api.errors import from_code, not_found
from derle.api.schemas import (
    TableDiff,
    TableSummary,
    TransformKindCount,
    TransformListItem,
    TransformPage,
    UploadDetail,
    UploadListItem,
    UploadOut,
    VersionOut,
)
from derle.config import Settings
from derle.domain.models import PipelineEvent
from derle.llm.base import LLMProvider
from derle.services import queries, review
from derle.services.ingest import IngestError, UploadResult, ingest_file
from derle.storage.db import Database

router = APIRouter(tags=["uploads"])
log = logging.getLogger(__name__)


def _to_out(result: UploadResult) -> UploadOut:
    return UploadOut(
        upload_id=result.upload_id,
        version_id=result.version_id,
        filename=result.filename,
        events=result.events,
        tables=[
            TableSummary(
                table_id=t.table_id,
                dataset_id=t.dataset_id,
                sheet=t.sheet,
                created_dataset=t.created_dataset,
                columns=t.columns,
                rows_total=t.rows_total,
                rows_imported=t.rows_imported,
                duplicates=t.duplicates,
                skipped=t.skipped,
                transforms=t.transforms,
            )
            for t in result.tables
        ],
    )


async def _read_upload(
    file: UploadFile, settings: Settings, db: Database, workspace_id: int
) -> bytes:
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail={"code": "too_large"})
    with db.read() as cur:
        if cur.execute("SELECT 1 FROM workspaces WHERE id = ?", [workspace_id]).fetchone() is None:
            raise not_found("workspace_not_found")
    return data


@router.post("/workspaces/{workspace_id}/uploads", status_code=status.HTTP_201_CREATED)
async def upload_file(
    workspace_id: int,
    file: Annotated[UploadFile, File()],
    db: DbDep,
    settings: SettingsDep,
    llm: LlmDep,
    dataset_id: Annotated[int | None, Query()] = None,
) -> UploadOut:
    data = await _read_upload(file, settings, db, workspace_id)
    try:
        result = await asyncio.to_thread(
            ingest_file,
            db,
            workspace_id=workspace_id,
            data=data,
            filename=file.filename or "upload",
            llm=llm,
            blob_dir=settings.blob_dir,
            target_dataset_id=dataset_id,
        )
    except IngestError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "upload_id": exc.upload_id},
        ) from exc
    return _to_out(result)


def _sse(event: str, payload: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


@router.post(
    "/workspaces/{workspace_id}/uploads/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def upload_file_stream(
    workspace_id: int,
    file: Annotated[UploadFile, File()],
    db: DbDep,
    settings: SettingsDep,
    llm: LlmDep,
) -> StreamingResponse:
    """Same as the plain upload, but streams pipeline events as Server-Sent Events.

    Events: ``event`` (one per pipeline step), then exactly one of ``result`` (an
    ``UploadOut``) or ``error`` (``{code, upload_id}``).
    """
    data = await _read_upload(file, settings, db, workspace_id)
    filename = file.filename or "upload"
    return StreamingResponse(
        _stream_ingest(db, llm, settings, workspace_id, data, filename),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_ingest(
    db: Database,
    llm: LLMProvider,
    settings: Settings,
    workspace_id: int,
    data: bytes,
    filename: str,
) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, Any] | None] = asyncio.Queue()

    def put(item: tuple[str, Any] | None) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, item)

    def on_event(event: PipelineEvent) -> None:
        put(("event", event.model_dump(mode="json")))

    def work() -> None:
        try:
            result = ingest_file(
                db,
                workspace_id=workspace_id,
                data=data,
                filename=filename,
                llm=llm,
                blob_dir=settings.blob_dir,
                on_event=on_event,
            )
            put(("result", _to_out(result).model_dump(mode="json")))
        except IngestError as exc:
            put(("error", {"code": exc.code, "upload_id": exc.upload_id}))
        except Exception:
            log.exception("upload processing failed")
            put(("error", {"code": "internal_error", "upload_id": None}))
        finally:
            put(None)

    task = loop.run_in_executor(None, work)
    while (item := await queue.get()) is not None:
        yield _sse(*item)
    await task


@router.get("/workspaces/{workspace_id}/uploads")
def list_uploads(workspace_id: int, db: DbDep) -> list[UploadListItem]:
    with db.read() as cur:
        return [UploadListItem(**u) for u in queries.list_uploads(cur, workspace_id)]


@router.get("/uploads/{upload_id}")
def get_upload(upload_id: int, db: DbDep) -> UploadDetail:
    with db.read() as cur:
        upload = queries.get_upload(cur, upload_id)
    if upload is None:
        raise not_found("upload_not_found")
    return UploadDetail(**upload)


@router.post("/uploads/{upload_id}/undo")
def undo_upload(upload_id: int, db: DbDep) -> VersionOut:
    try:
        with db.transaction() as cur:
            return VersionOut(version_id=review.undo_upload(cur, upload_id))
    except review.ReviewError as exc:
        raise from_code(exc.code) from exc


@router.get("/tables/{table_id}/diff")
def table_diff(
    table_id: int,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TableDiff:
    """Before/after view: every raw row (including skipped ones) next to its clean record."""
    with db.read() as cur:
        diff = review.table_diff(cur, table_id, offset=offset, limit=limit)
    if diff is None:
        raise not_found("table_not_found")
    return TableDiff(**diff)


@router.get("/tables/{table_id}/transformations")
def list_transformations(
    table_id: int,
    db: DbDep,
    kind: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransformPage:
    with db.read() as cur:
        items, total = review.list_transformations(
            cur, table_id, kind=kind, limit=limit, offset=offset
        )
        summary = review.transformation_summary(cur, table_id)
    return TransformPage(
        total=total,
        summary=[TransformKindCount(**s) for s in summary],
        items=[TransformListItem(**i) for i in items],
    )


@router.post("/transformations/{transformation_id}/undo")
def undo_transformation(transformation_id: int, db: DbDep) -> VersionOut:
    try:
        with db.transaction() as cur:
            return VersionOut(version_id=review.undo_transformation(cur, transformation_id))
    except review.ReviewError as exc:
        raise from_code(exc.code) from exc
