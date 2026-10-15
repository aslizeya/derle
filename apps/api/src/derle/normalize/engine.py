"""Apply role-specific normalizers to a whole table and log every change.

Column-level context is inferred first (number style, date order, default year) so that
ambiguous single values ("1.250", "03/04") are resolved consistently with their siblings.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from derle.domain.models import (
    CANONICAL_ROLES,
    ROLE_DTYPE,
    CellTransform,
    ColumnInference,
    ColumnRole,
    DType,
    NormalizedCell,
    TransformKind,
)
from derle.ingest.base import NativeValue, RawRow, RawTable
from derle.normalize.tr.dates import (
    DateContext,
    DateOrder,
    infer_date_order,
    parse_date,
    year_from_filename,
)
from derle.normalize.tr.names import combine_first_last, parse_name
from derle.normalize.tr.numbers import NumberStyle, format_decimal, infer_number_style, parse_number
from derle.normalize.tr.phones import parse_phone
from derle.normalize.tr.tckn import clean_tckn
from derle.normalize.tr.text import collapse_ws
from derle.semantics.dictionary import normalize_header

# Excel stores dates as days since 1899-12-30; plausible business dates fall in this window.
_EXCEL_SERIAL_RANGE = (32874, 54789)  # 1990-01-01 .. 2049-12-31


@dataclass(slots=True)
class ColumnContext:
    number_style: NumberStyle | None = None
    date_ctx: DateContext = field(default_factory=DateContext)


@dataclass(slots=True)
class FieldSpec:
    """A target field of the normalized row, fed by one or more source columns."""

    key: str  # canonical key: role name, or "description:urun" for free-text columns
    role: ColumnRole
    label: str
    src_cols: list[int]

    @property
    def dtype(self) -> DType:
        return ROLE_DTYPE.get(self.role, DType.TEXT)


@dataclass(slots=True)
class NormalizedRow:
    row_index: int
    cells: dict[str, NormalizedCell]


def plan_fields(inferences: list[ColumnInference]) -> list[FieldSpec]:
    specs: list[FieldSpec] = []
    first = next((i for i in inferences if i.role == ColumnRole.FIRST_NAME), None)
    last = next((i for i in inferences if i.role == ColumnRole.LAST_NAME), None)
    if first and last:
        specs.append(
            FieldSpec("party", ColumnRole.PARTY, "party", [first.col_index, last.col_index])
        )

    seen: set[str] = {s.key for s in specs}
    for inf in inferences:
        role = inf.role
        if role in {ColumnRole.FIRST_NAME, ColumnRole.LAST_NAME}:
            if first and last:
                continue
            role = ColumnRole.PARTY  # a lone "Ad" column is the party name
        if role == ColumnRole.UNKNOWN:
            role = ColumnRole.DESCRIPTION
        if role in CANONICAL_ROLES:
            key = role.value
        else:
            key = f"{role.value}:{normalize_header(inf.header) or inf.col_index}"
        if key in seen:
            key = f"{key}:{inf.col_index}"
        seen.add(key)
        specs.append(FieldSpec(key, role, inf.header, [inf.col_index]))
    return specs


def build_context(table: RawTable, spec: FieldSpec, filename: str, today: date) -> ColumnContext:
    values = [v for c in spec.src_cols for v in _column_text(table, c)]
    ctx = ColumnContext()
    if spec.dtype == DType.NUMBER:
        ctx.number_style = infer_number_style(values)
    elif spec.dtype == DType.DATE:
        order = infer_date_order(values)
        years = Counter(
            p.value.year
            for v in values
            if (p := parse_date(v, DateContext(order=order))) is not None and not p.year_inferred
        )
        default_year = (
            year_from_filename(filename)
            or (years.most_common(1)[0][0] if years else None)
            or today.year
        )
        ctx.date_ctx = DateContext(default_year=default_year, order=order)
    return ctx


def _column_text(table: RawTable, col: int) -> list[str]:
    """Typed-in text of a column. Excel-native values are excluded: their text form is
    produced by us (``1250.5``) and would wrongly vote for the English number style."""
    out: list[str] = []
    for row in table.rows:
        value = row.cells[col]
        native = row.native[col] if row.native is not None else None
        if value is not None and value.strip() and native is None:
            out.append(value)
    return out


def normalize_table(
    table: RawTable,
    specs: list[FieldSpec],
    *,
    filename: str,
    today: date | None = None,
) -> list[NormalizedRow]:
    today = today or date.today()
    contexts = {s.key: build_context(table, s, filename, today) for s in specs}
    out: list[NormalizedRow] = []
    for row in table.rows:
        cells = {s.key: normalize_cell(row, s, contexts[s.key]) for s in specs}
        out.append(NormalizedRow(row_index=row.index, cells=cells))
    return out


def normalize_cell(row: RawRow, spec: FieldSpec, ctx: ColumnContext) -> NormalizedCell:
    if len(spec.src_cols) > 1:  # split first/last name
        raw = combine_first_last(*(row.cells[c] for c in spec.src_cols[:2]))
        cell = _normalize_name(raw, spec.src_cols)
        if raw is not None and cell.text is not None:
            cell.transforms.insert(
                0, CellTransform(kind=TransformKind.NAMES_COMBINED, before=None, after=raw)
            )
        return cell

    col = spec.src_cols[0]
    raw = row.cells[col]
    native = row.native[col] if row.native is not None else None
    if raw is None or not raw.strip():
        return NormalizedCell(raw=raw, src_cols=spec.src_cols)

    match spec.role:
        case ColumnRole.DATE:
            return _normalize_date(raw, native, spec.src_cols, ctx)
        case (
            ColumnRole.AMOUNT
            | ColumnRole.DEBIT
            | ColumnRole.CREDIT
            | ColumnRole.BALANCE
            | ColumnRole.QUANTITY
        ):
            return _normalize_number(raw, native, spec.src_cols, ctx)
        case ColumnRole.PARTY:
            return _normalize_name(raw, spec.src_cols)
        case ColumnRole.PHONE:
            return _normalize_phone(raw, spec.src_cols)
        case ColumnRole.TCKN:
            digits = clean_tckn(raw)
            if digits is None:
                return _failed(raw, spec.src_cols, "invalid_tckn")
            return NormalizedCell(raw=raw, src_cols=spec.src_cols, text=digits)
        case _:
            return _normalize_text(raw, spec.src_cols)


def _failed(raw: str, src_cols: list[int], reason: str) -> NormalizedCell:
    text = collapse_ws(raw)
    return NormalizedCell(
        raw=raw,
        src_cols=src_cols,
        text=text,
        transforms=[
            CellTransform(
                kind=TransformKind.PARSE_FAILED,
                before=raw,
                after=None,
                confidence=0.0,
                detail={"reason": reason},
            )
        ],
    )


def _normalize_text(raw: str, src_cols: list[int]) -> NormalizedCell:
    text = collapse_ws(raw)
    transforms = []
    if text != raw:
        transforms.append(CellTransform(kind=TransformKind.TEXT_TRIMMED, before=raw, after=text))
    return NormalizedCell(raw=raw, src_cols=src_cols, text=text, transforms=transforms)


def _normalize_date(
    raw: str, native: NativeValue, src_cols: list[int], ctx: ColumnContext
) -> NormalizedCell:
    if isinstance(native, datetime):
        return NormalizedCell(raw=raw, src_cols=src_cols, day=native.date())
    if isinstance(native, date):
        return NormalizedCell(raw=raw, src_cols=src_cols, day=native)
    if isinstance(native, int | float) and not isinstance(native, bool):
        serial = int(native)
        if _EXCEL_SERIAL_RANGE[0] <= serial <= _EXCEL_SERIAL_RANGE[1]:
            day = date.fromordinal(date(1899, 12, 30).toordinal() + serial)
            return NormalizedCell(
                raw=raw,
                src_cols=src_cols,
                day=day,
                transforms=[
                    CellTransform(
                        kind=TransformKind.DATE_PARSED,
                        before=raw,
                        after=day.isoformat(),
                        detail={"source": "excel_serial"},
                    )
                ],
            )

    parsed = parse_date(raw, ctx.date_ctx)
    if parsed is None:
        return _failed(raw, src_cols, "not_a_date")
    confidence = 1.0
    detail: dict[str, object] = {}
    if parsed.ambiguous:
        confidence = 0.7
        detail["ambiguous_order"] = ctx.date_ctx.order.value
    if parsed.year_inferred:
        confidence = min(confidence, 0.8)
        detail["year_inferred"] = parsed.value.year
    transforms = []
    if raw.strip() != parsed.value.isoformat():
        transforms.append(
            CellTransform(
                kind=TransformKind.DATE_PARSED,
                before=raw,
                after=parsed.value.isoformat(),
                confidence=confidence,
                detail=detail,
            )
        )
    return NormalizedCell(raw=raw, src_cols=src_cols, day=parsed.value, transforms=transforms)


def _normalize_number(
    raw: str, native: NativeValue, src_cols: list[int], ctx: ColumnContext
) -> NormalizedCell:
    if isinstance(native, int | float) and not isinstance(native, bool):
        return NormalizedCell(raw=raw, src_cols=src_cols, number=Decimal(str(native)))

    parsed = parse_number(raw, ctx.number_style)
    if parsed is None:
        return _failed(raw, src_cols, "not_a_number")
    after = format_decimal(parsed.value)
    transforms: list[CellTransform] = []
    if parsed.currency is not None:
        transforms.append(
            CellTransform(
                kind=TransformKind.CURRENCY_STRIPPED,
                before=raw,
                after=after,
                detail={"currency": parsed.currency},
            )
        )
    if raw.strip() != after:
        detail: dict[str, object] = {"style": (ctx.number_style or NumberStyle.TR).value}
        if parsed.ambiguous:
            detail["ambiguous"] = True
        transforms.append(
            CellTransform(
                kind=TransformKind.NUMBER_PARSED,
                before=raw,
                after=after,
                confidence=0.75 if parsed.ambiguous else 1.0,
                detail=detail,
            )
        )
    return NormalizedCell(raw=raw, src_cols=src_cols, number=parsed.value, transforms=transforms)


def _normalize_name(raw: str | None, src_cols: list[int]) -> NormalizedCell:
    if raw is None or not raw.strip():
        return NormalizedCell(raw=raw, src_cols=src_cols)
    parsed = parse_name(raw)
    if parsed is None:
        return _normalize_text(raw, src_cols)
    transforms: list[CellTransform] = []
    if parsed.honorifics:
        transforms.append(
            CellTransform(
                kind=TransformKind.HONORIFIC_REMOVED,
                before=raw,
                after=parsed.display,
                detail={"removed": list(parsed.honorifics)}
                | ({"note": parsed.note} if parsed.note else {}),
            )
        )
    if parsed.display != collapse_ws(raw) and not parsed.honorifics:
        detail: dict[str, object] = {}
        if parsed.note:
            detail["note"] = parsed.note
        if parsed.reordered:
            detail["reordered"] = True
        transforms.append(
            CellTransform(
                kind=TransformKind.NAME_NORMALIZED, before=raw, after=parsed.display, detail=detail
            )
        )
    return NormalizedCell(raw=raw, src_cols=src_cols, text=parsed.display, transforms=transforms)


def _normalize_phone(raw: str, src_cols: list[int]) -> NormalizedCell:
    parsed = parse_phone(raw)
    if parsed is None:
        return _failed(raw, src_cols, "invalid_phone")
    transforms = []
    if raw.strip() != parsed.national:
        transforms.append(
            CellTransform(kind=TransformKind.PHONE_NORMALIZED, before=raw, after=parsed.national)
        )
    return NormalizedCell(raw=raw, src_cols=src_cols, text=parsed.national, transforms=transforms)


__all__ = [
    "ColumnContext",
    "DateOrder",
    "FieldSpec",
    "NormalizedRow",
    "build_context",
    "normalize_cell",
    "normalize_table",
    "plan_fields",
]
