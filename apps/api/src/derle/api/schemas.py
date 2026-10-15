"""Response models. They define the OpenAPI contract the frontend types are generated from."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from derle.domain.models import ColumnInference, PipelineEvent


class WorkspaceOut(BaseModel):
    id: int
    name: str
    is_demo: bool


class TableSummary(BaseModel):
    table_id: int
    dataset_id: int
    sheet: str | None
    created_dataset: bool
    columns: list[ColumnInference]
    rows_total: int
    rows_imported: int
    duplicates: int
    skipped: dict[str, int]
    transforms: dict[str, int]


class UploadOut(BaseModel):
    upload_id: int
    version_id: int
    filename: str
    tables: list[TableSummary]
    events: list[PipelineEvent]


class DatasetSummary(BaseModel):
    id: int
    name: str
    created_at: str
    records: int
    duplicates: int
    sources: int


class FieldOut(BaseModel):
    id: int
    key: str
    label: str
    role: str
    dtype: str
    position: int
    pii: str | None
    column: str


class DatasetOut(BaseModel):
    id: int
    workspace_id: int
    name: str
    fields: list[FieldOut]


class RecordsPage(BaseModel):
    total: int
    limit: int
    offset: int
    rows: list[dict[str, Any]]
    # record_id (as string, JSON keys) -> column -> mark
    marks: dict[str, dict[str, CellMark]] = {}


class ProvenanceOut(BaseModel):
    record_id: int
    field: dict[str, Any]
    value: Any
    original: str | None
    source: dict[str, Any]
    record_status: str
    duplicate_of: int | None
    transforms: list[dict[str, Any]]


class ErrorOut(BaseModel):
    code: str
    detail: str | None = None


# --- entity resolution ------------------------------------------------------------------------


class EvidenceOut(BaseModel):
    code: str
    weight: float
    value: float | str | None = None


class AliasOut(BaseModel):
    name: str
    count: int


class RecordFact(BaseModel):
    record_id: int
    filename: str | None = None
    sheet: str | None = None
    row: int | None = None
    name: str | None = None
    date: str | None = None
    amount: float | None = None
    debit: float | None = None
    credit: float | None = None


class EntitySummary(BaseModel):
    id: int
    workspace_id: int
    name: str
    record_count: int
    aliases: list[AliasOut]
    phones: list[str]
    first_date: str | None
    last_date: str | None
    totals: dict[str, float]
    samples: list[RecordFact]


class CardSide(BaseModel):
    profile: str
    entity: EntitySummary | None


class MatchCard(BaseModel):
    id: int
    score: float
    status: str
    evidence: list[EvidenceOut]
    left: CardSide
    right: CardSide


class MatchQueue(BaseModel):
    total: int
    cards: list[MatchCard]


class DecisionIn(BaseModel):
    decision: Literal["same", "different", "skip"]


class ResolutionOut(BaseModel):
    version_id: int
    entities: int
    pending: int


class UndoOut(ResolutionOut):
    candidate_id: int


class EntityListItem(BaseModel):
    id: int
    name: str
    record_count: int


class EntitiesPage(BaseModel):
    total: int
    items: list[EntityListItem]


# --- workspaces, uploads, review ------------------------------------------------------------


class WorkspaceSummary(BaseModel):
    id: int
    name: str
    is_demo: bool
    created_at: str
    datasets: int
    uploads: int
    records: int
    entities: int
    pending_matches: int


class UploadListItem(BaseModel):
    id: int
    filename: str
    status: str
    error_code: str | None
    created_at: str
    size_bytes: int
    tables: int
    records: int
    duplicates: int
    first_table_id: int | None
    dataset_id: int | None


class SourceColumnOut(BaseModel):
    col_index: int
    header: str
    role: str
    confidence: float
    engine: str | None = None
    reasons: list[dict[str, Any]] = []
    field_id: int | None


class UploadTableOut(BaseModel):
    id: int
    sheet: str | None
    header_row: int | None
    dataset_id: int | None
    columns: list[SourceColumnOut]
    transforms: dict[str, int]


class UploadDetail(BaseModel):
    id: int
    workspace_id: int
    version_id: int | None
    filename: str
    size_bytes: int
    status: str
    error_code: str | None
    created_at: str
    tables: list[UploadTableOut]


class TransformOut(BaseModel):
    id: int
    kind: str
    before: str | None
    after: str | None
    confidence: float
    detail: dict[str, Any]
    undone: bool


class DiffRecord(BaseModel):
    id: int
    status: str
    duplicate_of: int | None
    values: dict[str, Any]
    transforms: dict[str, list[TransformOut]]
    row_transforms: list[TransformOut] = []


class DiffRow(BaseModel):
    row_index: int
    raw: list[str | None]
    skip_reason: str | None
    record: DiffRecord | None


class TableDiff(BaseModel):
    table_id: int
    upload_id: int
    filename: str
    sheet: str | None
    header_row: int | None
    dataset_id: int
    columns: list[SourceColumnOut]
    fields: list[FieldOut]
    total_rows: int
    offset: int
    rows: list[DiffRow]


class TransformKindCount(BaseModel):
    kind: str
    count: int
    undone: int


class TransformListItem(TransformOut):
    record_id: int | None
    row_index: int | None
    field_key: str | None
    field_label: str | None


class TransformPage(BaseModel):
    total: int
    summary: list[TransformKindCount]
    items: list[TransformListItem]


class CellMark(BaseModel):
    state: Literal["changed", "original", "failed"]
    kinds: list[str]
    raw: str | None


class VersionOut(BaseModel):
    version_id: int


class DemoFile(BaseModel):
    name: str
    size: int


RecordsPage.model_rebuild()
