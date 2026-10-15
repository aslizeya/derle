"""Upload use case: bytes in, versioned clean records with provenance out.

    read grids → detect table → infer column roles (rules [+ LLM]) → choose dataset
    → normalize → drop exact duplicates → write raw rows, records, cells, transformations
    → rebuild the dataset view

Everything one upload writes is stamped with one ``version_id`` inside one transaction.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePath
from typing import Any

from derle.domain.models import (
    PII_ROLES,
    ColumnInference,
    PipelineEvent,
    TransformKind,
)
from derle.ingest import UnsupportedFileError, read_grids
from derle.ingest.base import RawGrid, RawTable
from derle.ingest.structure import detect_table
from derle.llm.base import LLMProvider, NullProvider
from derle.normalize.engine import FieldSpec, NormalizedRow, normalize_table, plan_fields
from derle.normalize.tr.numbers import format_decimal
from derle.semantics.infer import infer_table
from derle.semantics.llm_refine import refine_with_llm
from derle.services.entities import resolve_workspace
from derle.storage import repo
from derle.storage.db import Database
from derle.storage.repo import Cursor

EventSink = Callable[[PipelineEvent], None]

RAW_ROW_TYPES = {
    "table_id": "BIGINT", "row_index": "INTEGER", "cells": "VARCHAR[]", "skip_reason": "VARCHAR",
}  # fmt: skip
RECORD_TYPES = {
    "id": "BIGINT", "dataset_id": "BIGINT", "table_id": "BIGINT", "row_index": "INTEGER",
    "status": "VARCHAR", "duplicate_of": "BIGINT", "version_from": "BIGINT",
}  # fmt: skip
CELL_TYPES = {
    "record_id": "BIGINT", "field_id": "BIGINT", "value_text": "VARCHAR",
    "value_num": "DECIMAL(18, 4)", "value_date": "DATE", "raw_value": "VARCHAR",
    "src_cols": "INTEGER[]", "version_from": "BIGINT",
}  # fmt: skip
TRANSFORM_TYPES = {
    "record_id": "BIGINT", "field_id": "BIGINT", "kind": "VARCHAR", "before_value": "VARCHAR",
    "after_value": "VARCHAR", "confidence": "DOUBLE", "detail": "JSON", "version_id": "BIGINT",
    "table_id": "BIGINT",
}  # fmt: skip

# Reuse an existing dataset when this share of the new table's structured fields matches.
DATASET_MATCH_THRESHOLD = 0.5


@dataclass(slots=True)
class TableResult:
    table_id: int
    dataset_id: int
    sheet: str | None
    columns: list[ColumnInference]
    rows_total: int
    rows_imported: int
    duplicates: int
    skipped: dict[str, int]
    transforms: dict[str, int]
    created_dataset: bool


@dataclass(slots=True)
class UploadResult:
    upload_id: int
    version_id: int
    filename: str
    tables: list[TableResult] = field(default_factory=list)
    events: list[PipelineEvent] = field(default_factory=list)


class IngestError(Exception):
    def __init__(self, code: str, upload_id: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.upload_id = upload_id


def ingest_file(
    db: Database,
    *,
    workspace_id: int,
    data: bytes,
    filename: str,
    llm: LLMProvider | None = None,
    blob_dir: Path | None = None,
    target_dataset_id: int | None = None,
    on_event: EventSink | None = None,
    today: date | None = None,
) -> UploadResult:
    llm = llm or NullProvider()
    events: list[PipelineEvent] = []

    def emit(event_code: str, **params: Any) -> None:
        event = PipelineEvent(code=event_code, params=params)
        events.append(event)
        if on_event is not None:
            on_event(event)

    filename = PurePath(filename).name or "upload"
    sha = hashlib.sha256(data).hexdigest()
    if blob_dir is not None:
        blob_dir.mkdir(parents=True, exist_ok=True)
        (blob_dir / sha).write_bytes(data)

    emit("file_received", filename=filename, size=len(data))
    try:
        grids = read_grids(data, filename)
    except UnsupportedFileError as exc:
        with db.transaction() as cur:
            upload_id = repo.insert_returning_id(
                cur,
                "INSERT INTO uploads (workspace_id, filename, sha256, size_bytes, status, "
                "error_code) VALUES (?, ?, ?, ?, 'failed', ?)",
                [workspace_id, filename, sha, len(data), exc.code],
            )
        emit("failed", error=exc.code)
        raise IngestError(exc.code, upload_id) from exc

    emit("file_read", sheets=len(grids), encoding=grids[0].meta.get("encoding"))

    with db.transaction() as cur:
        version_id = repo.create_version(
            cur, workspace_id, "upload", filename, {"filename": filename}
        )
        upload_id = repo.insert_returning_id(
            cur,
            "INSERT INTO uploads (workspace_id, version_id, filename, sha256, size_bytes, status) "
            "VALUES (?, ?, ?, ?, ?, 'processing')",
            [workspace_id, version_id, filename, sha, len(data)],
        )
        result = UploadResult(upload_id=upload_id, version_id=version_id, filename=filename)
        for grid in grids:
            table_result = _ingest_grid(
                cur,
                grid,
                workspace_id=workspace_id,
                upload_id=upload_id,
                version_id=version_id,
                filename=filename,
                llm=llm,
                target_dataset_id=target_dataset_id,
                today=today or date.today(),
                emit=emit,
            )
            if table_result is not None:
                result.tables.append(table_result)
        resolution = resolve_workspace(cur, workspace_id, version_id)
        emit(
            "entities_resolved",
            entities=resolution.entities,
            auto_merged=resolution.auto_merges,
            pending=resolution.pending,
        )
        cur.execute("UPDATE uploads SET status = 'done' WHERE id = ?", [upload_id])

    emit(
        "done",
        upload_id=upload_id,
        rows=sum(t.rows_imported for t in result.tables),
        duplicates=sum(t.duplicates for t in result.tables),
    )
    result.events = events
    return result


def _ingest_grid(
    cur: Cursor,
    grid: RawGrid,
    *,
    workspace_id: int,
    upload_id: int,
    version_id: int,
    filename: str,
    llm: LLMProvider,
    target_dataset_id: int | None,
    today: date,
    emit: Callable[..., None],
) -> TableResult | None:
    table = detect_table(grid)
    emit(
        "table_detected",
        sheet=grid.sheet,
        header_row=table.header_row,
        columns=len(table.headers),
        rows=len(table.rows),
    )
    skipped_counts: dict[str, int] = {}
    for s in table.skipped:
        skipped_counts[s.reason] = skipped_counts.get(s.reason, 0) + 1
    for reason, count in skipped_counts.items():
        emit("rows_skipped", reason=reason, count=count)

    columns = refine_with_llm(table, infer_table(table), llm)
    for col in columns:
        emit(
            "column_recognized",
            header=col.header,
            role=col.role,
            confidence=col.confidence,
            engine=col.engine,
        )

    specs = plan_fields(columns)
    rows = normalize_table(table, specs, filename=filename, today=today)

    dataset_id, created = _choose_dataset(
        cur, workspace_id, specs, filename, grid.sheet, target_dataset_id
    )
    emit("dataset_created" if created else "dataset_matched", dataset_id=dataset_id)
    field_ids = _ensure_fields(cur, dataset_id, specs)

    table_id = repo.insert_returning_id(
        cur,
        "INSERT INTO upload_tables (upload_id, sheet, header_row, dataset_id, meta) "
        "VALUES (?, ?, ?, ?, CAST(? AS JSON))",
        [upload_id, grid.sheet, table.header_row, dataset_id, repo.to_json(table.meta)],
    )
    _write_raw_rows(cur, table_id, grid, table)
    _write_source_columns(cur, table_id, columns, specs, field_ids)

    duplicates_of = _find_duplicates(cur, dataset_id, rows, specs)
    transform_counts = _write_records(
        cur, table_id, dataset_id, version_id, rows, specs, field_ids, duplicates_of
    )
    for kind, count in sorted(transform_counts.items()):
        if kind != TransformKind.DUPLICATE_REMOVED:
            emit("values_normalized", kind=kind, count=count)
    if duplicates_of:
        emit("duplicates_removed", count=len(duplicates_of))

    repo.rebuild_dataset_view(cur, dataset_id)
    return TableResult(
        table_id=table_id,
        dataset_id=dataset_id,
        sheet=grid.sheet,
        columns=columns,
        rows_total=len(table.rows),
        rows_imported=len(rows) - len(duplicates_of),
        duplicates=len(duplicates_of),
        skipped=skipped_counts,
        transforms=transform_counts,
        created_dataset=created,
    )


def _choose_dataset(
    cur: Cursor,
    workspace_id: int,
    specs: list[FieldSpec],
    filename: str,
    sheet: str | None,
    target_dataset_id: int | None,
) -> tuple[int, bool]:
    if target_dataset_id is not None:
        return target_dataset_id, False
    # Only structured fields count (free-text columns vary too much between files), and the
    # money roles count as one family: a ledger that switched from a single "Tutar" column to
    # "Borç / Ödeme" in February is still the same ledger.
    new_keys = _schema_signature(s.key for s in specs)
    best_id, best_score = None, 0.0
    for dataset_id, keys in repo.dataset_field_keys(cur, workspace_id).items():
        structured = _schema_signature(keys)
        if not new_keys or not structured:
            continue
        score = len(new_keys & structured) / len(new_keys | structured)
        if score > best_score:
            best_id, best_score = dataset_id, score
    if best_id is not None and best_score >= DATASET_MATCH_THRESHOLD:
        return best_id, False
    name = PurePath(filename).stem if sheet is None else f"{PurePath(filename).stem} – {sheet}"
    dataset_id = repo.insert_returning_id(
        cur, "INSERT INTO datasets (workspace_id, name) VALUES (?, ?)", [workspace_id, name]
    )
    return dataset_id, True


_MONEY_KEYS = frozenset({"amount", "debit", "credit", "balance"})


def _schema_signature(keys: Iterable[str]) -> set[str]:
    return {"money" if k in _MONEY_KEYS else k for k in keys if ":" not in k}


def _ensure_fields(cur: Cursor, dataset_id: int, specs: list[FieldSpec]) -> dict[str, int]:
    existing = {f["key"]: int(f["id"]) for f in repo.get_fields(cur, dataset_id)}
    position = len(existing)
    for spec in specs:
        if spec.key in existing:
            continue
        existing[spec.key] = repo.insert_returning_id(
            cur,
            "INSERT INTO fields (dataset_id, key, label, role, dtype, position, pii) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                dataset_id,
                spec.key,
                spec.label,
                spec.role.value,
                spec.dtype.value,
                position,
                PII_ROLES.get(spec.role),
            ],
        )
        position += 1
    return existing


def _write_raw_rows(cur: Cursor, table_id: int, grid: RawGrid, table: RawTable) -> None:
    reasons = {s.index: s.reason for s in table.skipped}
    repo.bulk_insert(
        cur,
        "raw_rows",
        {
            "table_id": [table_id] * len(grid.rows),
            "row_index": [r.index for r in grid.rows],
            "cells": [list(r.cells) for r in grid.rows],
            "skip_reason": [reasons.get(r.index) for r in grid.rows],
        },
        RAW_ROW_TYPES,
    )


def _write_source_columns(
    cur: Cursor,
    table_id: int,
    columns: list[ColumnInference],
    specs: list[FieldSpec],
    field_ids: dict[str, int],
) -> None:
    field_by_col = {c: field_ids[s.key] for s in specs for c in s.src_cols}
    for col in columns:
        cur.execute(
            "INSERT INTO source_columns (table_id, col_index, header, role, confidence, engine, "
            "reasons, field_id) VALUES (?, ?, ?, ?, ?, ?, CAST(? AS JSON), ?)",
            [
                table_id,
                col.col_index,
                col.header,
                col.role.value,
                col.confidence,
                col.engine,
                repo.to_json([r.model_dump() for r in col.reasons]),
                field_by_col.get(col.col_index),
            ],
        )


def _signature(cells: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((k, str(v)) for k, v in cells.items() if v is not None))


def _row_values(row: NormalizedRow) -> dict[str, Any]:
    return {
        key: cell.day or (format_decimal(cell.number) if cell.number is not None else cell.text)
        for key, cell in row.cells.items()
    }


def _find_duplicates(
    cur: Cursor, dataset_id: int, rows: list[NormalizedRow], specs: list[FieldSpec]
) -> dict[int, int | None]:
    """Map ``row_index -> duplicate_of record id`` (``None`` = duplicate within this file).

    Only exact duplicates of the normalized values count here. Fuzzy "same customer"
    matching is entity resolution and is handled separately, with a review queue.
    """
    keys = [s.key for s in specs]
    existing: dict[tuple[tuple[str, str], ...], int] = {}
    if keys:
        current = repo.get_fields(cur, dataset_id)
        by_id = {int(f["id"]): f["key"] for f in current if f["key"] in keys}
        records: dict[int, dict[str, Any]] = {}
        for record_id, field_id, text, num, day in cur.execute(
            "SELECT r.id, c.field_id, c.value_text, c.value_num, c.value_date FROM records r "
            "JOIN cells c ON c.record_id = r.id AND c.version_to IS NULL "
            "WHERE r.dataset_id = ? AND r.version_to IS NULL AND r.status = 'active'",
            [dataset_id],
        ).fetchall():
            if field_id in by_id:
                value = day or (format_decimal(num) if num is not None else text)
                records.setdefault(int(record_id), {})[by_id[field_id]] = value
        for record_id, values in records.items():
            full = {k: values.get(k) for k in keys}
            existing.setdefault(_signature(full), record_id)

    seen_in_file: set[tuple[tuple[str, str], ...]] = set()
    duplicates: dict[int, int | None] = {}
    for row in rows:
        sig = _signature(_row_values(row))
        if not sig:
            continue
        if sig in existing:
            duplicates[row.row_index] = existing[sig]
        elif sig in seen_in_file:
            duplicates[row.row_index] = None
        else:
            seen_in_file.add(sig)
    return duplicates


def _write_records(
    cur: Cursor,
    table_id: int,
    dataset_id: int,
    version_id: int,
    rows: list[NormalizedRow],
    specs: list[FieldSpec],
    field_ids: dict[str, int],
    duplicates_of: dict[int, int | None],
) -> dict[str, int]:
    record_ids = repo.allocate_ids(cur, len(rows))
    first_record_by_sig: dict[tuple[tuple[str, str], ...], int] = {}

    rec: dict[str, list[Any]] = {k: [] for k in ("id", "row_index", "status", "duplicate_of")}
    cell: dict[str, list[Any]] = {
        k: [] for k in ("record_id", "field_id", "value_text", "value_num", "value_date",
                        "raw_value", "src_cols")
    }  # fmt: skip
    tr: dict[str, list[Any]] = {
        k: [] for k in ("record_id", "field_id", "kind", "before_value", "after_value",
                        "confidence", "detail")
    }  # fmt: skip
    counts: dict[str, int] = {}

    for record_id, row in zip(record_ids, rows, strict=True):
        sig = _signature(_row_values(row))
        is_dup = row.row_index in duplicates_of
        dup_of = duplicates_of.get(row.row_index) if is_dup else None
        if is_dup and dup_of is None:
            dup_of = first_record_by_sig.get(sig)
        if not is_dup and sig:
            first_record_by_sig.setdefault(sig, record_id)

        rec["id"].append(record_id)
        rec["row_index"].append(row.row_index)
        rec["status"].append("duplicate" if is_dup else "active")
        rec["duplicate_of"].append(dup_of)
        if is_dup:
            _append_transform(
                tr, counts, record_id, None, TransformKind.DUPLICATE_REMOVED, None, None, 1.0,
                {"duplicate_of": dup_of},
            )  # fmt: skip

        for spec in specs:
            nc = row.cells[spec.key]
            field_id = field_ids[spec.key]
            cell["record_id"].append(record_id)
            cell["field_id"].append(field_id)
            cell["value_text"].append(nc.text)
            cell["value_num"].append(format_decimal(nc.number) if nc.number is not None else None)
            cell["value_date"].append(nc.day)
            cell["raw_value"].append(nc.raw)
            cell["src_cols"].append(nc.src_cols)
            for t in nc.transforms:
                _append_transform(
                    tr, counts, record_id, field_id, t.kind, t.before, t.after, t.confidence,
                    t.detail,
                )  # fmt: skip

    n, m, k = len(rows), len(cell["record_id"]), len(tr["record_id"])
    repo.bulk_insert(
        cur,
        "records",
        {
            **rec,
            "dataset_id": [dataset_id] * n,
            "table_id": [table_id] * n,
            "version_from": [version_id] * n,
        },
        RECORD_TYPES,
    )
    repo.bulk_insert(cur, "cells", {**cell, "version_from": [version_id] * m}, CELL_TYPES)
    repo.bulk_insert(
        cur,
        "transformations",
        {**tr, "version_id": [version_id] * k, "table_id": [table_id] * k},
        TRANSFORM_TYPES,
    )
    return counts


def _append_transform(
    tr: dict[str, list[Any]],
    counts: dict[str, int],
    record_id: int,
    field_id: int | None,
    kind: TransformKind,
    before: str | None,
    after: str | None,
    confidence: float,
    detail: dict[str, Any],
) -> None:
    tr["record_id"].append(record_id)
    tr["field_id"].append(field_id)
    tr["kind"].append(kind.value)
    tr["before_value"].append(before)
    tr["after_value"].append(after)
    tr["confidence"].append(confidence)
    tr["detail"].append(repo.to_json(detail))
    counts[kind.value] = counts.get(kind.value, 0) + 1
