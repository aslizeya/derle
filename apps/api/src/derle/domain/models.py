"""Core domain types shared across the pipeline, storage and API layers.

User-facing text is never produced here. Explanations travel as ``Reason``/``PipelineEvent``
codes with parameters, and the frontend renders them through i18n message catalogs.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ColumnRole(StrEnum):
    PARTY = "party"  # a person or company: customer, supplier...
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    DATE = "date"
    AMOUNT = "amount"
    DEBIT = "debit"  # "borç": the party owes this
    CREDIT = "credit"  # "alacak/ödeme": the party paid this
    BALANCE = "balance"
    QUANTITY = "quantity"
    PHONE = "phone"
    TCKN = "tckn"
    EMAIL = "email"
    DESCRIPTION = "description"
    CATEGORY = "category"
    IDENTIFIER = "identifier"
    UNKNOWN = "unknown"


class DType(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"


ROLE_DTYPE: dict[ColumnRole, DType] = {
    ColumnRole.DATE: DType.DATE,
    ColumnRole.AMOUNT: DType.NUMBER,
    ColumnRole.DEBIT: DType.NUMBER,
    ColumnRole.CREDIT: DType.NUMBER,
    ColumnRole.BALANCE: DType.NUMBER,
    ColumnRole.QUANTITY: DType.NUMBER,
}

# Roles that map onto a single canonical field per dataset. Free-text roles instead keep one
# field per distinct source header, so "Ürün" and "Not" do not collapse into one column.
CANONICAL_ROLES: frozenset[ColumnRole] = frozenset(
    {
        ColumnRole.PARTY,
        ColumnRole.DATE,
        ColumnRole.AMOUNT,
        ColumnRole.DEBIT,
        ColumnRole.CREDIT,
        ColumnRole.BALANCE,
        ColumnRole.QUANTITY,
        ColumnRole.PHONE,
        ColumnRole.TCKN,
        ColumnRole.EMAIL,
    }
)

PII_ROLES: dict[ColumnRole, str] = {
    ColumnRole.PHONE: "phone",
    ColumnRole.TCKN: "tckn",
    ColumnRole.EMAIL: "email",
}


class Reason(BaseModel):
    """A machine-readable explanation, e.g. ``header_match{keyword: "tarih"}``."""

    code: str
    params: dict[str, Any] = Field(default_factory=dict)


class ColumnInference(BaseModel):
    col_index: int
    header: str
    role: ColumnRole
    confidence: float = Field(ge=0, le=1)
    reasons: list[Reason] = Field(default_factory=list)
    engine: str = "rules"  # "rules" | "llm"


class TransformKind(StrEnum):
    DATE_PARSED = "date_parsed"
    NUMBER_PARSED = "number_parsed"
    CURRENCY_STRIPPED = "currency_stripped"
    NAME_NORMALIZED = "name_normalized"
    HONORIFIC_REMOVED = "honorific_removed"
    NAMES_COMBINED = "names_combined"
    PHONE_NORMALIZED = "phone_normalized"
    TEXT_TRIMMED = "text_trimmed"
    PARSE_FAILED = "parse_failed"
    DUPLICATE_REMOVED = "duplicate_removed"


class CellTransform(BaseModel):
    kind: TransformKind
    before: str | None
    after: str | None
    confidence: float = 1.0
    detail: dict[str, Any] = Field(default_factory=dict)


class NormalizedCell(BaseModel):
    """One clean value plus everything needed to explain where it came from."""

    raw: str | None
    src_cols: list[int]
    text: str | None = None
    number: Decimal | None = None
    day: date | None = None
    transforms: list[CellTransform] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.text is None and self.number is None and self.day is None


class PipelineEvent(BaseModel):
    """Progress signal emitted while an upload is processed (streamed to the UI via SSE)."""

    code: str
    params: dict[str, Any] = Field(default_factory=dict)
