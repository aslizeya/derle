from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status

from derle.api.deps import DbDep
from derle.api.errors import not_found
from derle.api.schemas import (
    DecisionIn,
    EntitiesPage,
    EntityListItem,
    EntitySummary,
    MatchCard,
    MatchQueue,
    ResolutionOut,
    UndoOut,
)
from derle.services import entities

router = APIRouter(tags=["matching"])


@router.get("/workspaces/{workspace_id}/matches")
def list_matches(
    workspace_id: int,
    db: DbDep,
    match_status: Annotated[
        Literal["pending", "accepted", "rejected", "skipped"], Query(alias="status")
    ] = "pending",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MatchQueue:
    with db.read() as cur:
        cards, total = entities.list_candidates(cur, workspace_id, status=match_status, limit=limit)
    return MatchQueue(total=total, cards=[MatchCard(**c) for c in cards])


@router.post("/matches/{candidate_id}/decision")
def decide_match(candidate_id: int, body: DecisionIn, db: DbDep) -> ResolutionOut:
    try:
        with db.transaction() as cur:
            version_id, summary = entities.decide(cur, candidate_id, body.decision)
    except entities.MatchError as exc:
        code = status.HTTP_404_NOT_FOUND if exc.code == "candidate_not_found" else 409
        raise HTTPException(code, detail={"code": exc.code}) from exc
    return ResolutionOut(version_id=version_id, entities=summary.entities, pending=summary.pending)


@router.post("/workspaces/{workspace_id}/matches/undo")
def undo_match(workspace_id: int, db: DbDep) -> UndoOut:
    try:
        with db.transaction() as cur:
            version_id, candidate_id, summary = entities.undo_last_decision(cur, workspace_id)
    except entities.MatchError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"code": exc.code}) from exc
    return UndoOut(
        version_id=version_id,
        candidate_id=candidate_id,
        entities=summary.entities,
        pending=summary.pending,
    )


@router.get("/workspaces/{workspace_id}/entities")
def list_entities(
    workspace_id: int,
    db: DbDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EntitiesPage:
    with db.read() as cur:
        items, total = entities.list_entities(
            cur, workspace_id, limit=limit, offset=offset, query=q
        )
    return EntitiesPage(total=total, items=[EntityListItem(**i) for i in items])


@router.get("/entities/{entity_id}")
def get_entity(entity_id: int, db: DbDep) -> EntitySummary:
    with db.read() as cur:
        summary = entities.entity_summary(cur, entity_id, samples=50)
    if summary is None:
        raise not_found("entity_not_found")
    return EntitySummary(**summary)
