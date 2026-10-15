"""Reader contracts.

A :class:`SourceReader` turns bytes into one or more :class:`RawGrid` objects: untouched
rows of cells exactly as they appear in the source. Structure detection (where the header
is, which rows are titles or totals) happens afterwards in :mod:`derle.ingest.structure`, so
future readers (WhatsApp exports, OCR of notebook photos) only need to produce grids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

NativeValue = int | float | date | datetime | bool | None


class UnsupportedFileError(ValueError):
    """Raised when a file cannot be read; ``code`` is an i18n key for the UI."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(slots=True)
class RawRow:
    index: int  # 1-based row number as the user sees it in Excel / a text editor
    cells: list[str | None]
    # Typed values when the source carries them (Excel numbers and dates). Normalizers prefer
    # these over re-parsing text, which avoids locale guessing for Excel numeric cells.
    native: list[NativeValue] | None = None

    def is_empty(self) -> bool:
        return all(c is None or not c.strip() for c in self.cells)


@dataclass(slots=True)
class RawGrid:
    sheet: str | None
    rows: list[RawRow]
    meta: dict[str, str] = field(default_factory=dict)  # encoding, delimiter, ...


@dataclass(slots=True)
class SkippedRow:
    index: int
    reason: str  # "empty" | "title" | "total" | "repeated_header"


@dataclass(slots=True)
class RawTable:
    """A grid after structure detection: a header plus data rows."""

    sheet: str | None
    header_row: int | None  # RawRow.index of the header, None if the file had no header
    headers: list[str]
    col_indexes: list[int]  # original column position of each kept column
    rows: list[RawRow]
    skipped: list[SkippedRow] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)

    def column_values(self, position: int) -> list[str]:
        """Non-empty text values of the column at ``position`` (index into ``headers``)."""
        col = self.col_indexes[position]
        out: list[str] = []
        for row in self.rows:
            value = row.cells[col] if col < len(row.cells) else None
            if value is not None and value.strip():
                out.append(value)
        return out


class SourceReader(Protocol):
    extensions: tuple[str, ...]

    def read(self, data: bytes, filename: str) -> list[RawGrid]: ...
