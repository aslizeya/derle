"""Find the table inside a grid: skip title rows, pick the header, drop totals and blanks.

Hand-made spreadsheets rarely start at A1. A typical file looks like::

    1 | KARDEŞLER BAKKALİYE - MART 2026 VERESİYE   |          |
    2 |                                             |          |
    3 | Tarih        | Müşteri       | Tutar        | Açıklama |
    4 | 01.03.2026   | Ahmet bey     | 1.250,00 TL  | ekmek    |
    ...
   40 | TOPLAM       |               | 48.300,00    |          |

The header is scored by vocabulary hits and "text-likeness"; data rows follow it.
"""

from __future__ import annotations

from derle.ingest.base import RawGrid, RawRow, RawTable, SkippedRow
from derle.normalize.tr.dates import parse_date
from derle.normalize.tr.numbers import parse_number
from derle.normalize.tr.text import collapse_ws, fold
from derle.semantics.dictionary import TOTAL_ROW_MARKERS, match_header, normalize_header

HEADER_SCAN_ROWS = 25


def _looks_like_value(cell: str) -> bool:
    return parse_number(cell) is not None or parse_date(cell) is not None


def _has_value(cell: str | None) -> bool:
    return cell is not None and bool(cell.strip())


def _header_score(row: RawRow, width: int) -> tuple[float, int, bool]:
    """Return ``(score, vocabulary_hits, all_textual)``."""
    cells = [c for c in row.cells if c is not None and c.strip()]
    if len(cells) < 2:
        return 0.0, 0, False
    hits = sum(1 for c in cells if match_header(c) is not None)
    textual = sum(1 for c in cells if not _looks_like_value(c))
    unique = len({fold(c) for c in cells}) == len(cells)
    fill = len(cells) / max(width, 1)
    score = hits * 2.0 + (textual / len(cells)) * fill + (0.5 if unique else 0.0)
    return score, hits, textual == len(cells)


def _next_row_has_values(rows: list[RawRow], after: RawRow) -> bool:
    following = rows[rows.index(after) + 1 :]
    nxt = next((r for r in following if not r.is_empty()), None)
    if nxt is None:
        return False
    return any(c is not None and c.strip() and _looks_like_value(c) for c in nxt.cells)


def _is_total_row(row: RawRow) -> bool:
    texts = [fold(c) for c in row.cells if c is not None and c.strip()]
    return bool(texts) and any(t.startswith(m) for t in texts[:2] for m in TOTAL_ROW_MARKERS)


def detect_table(grid: RawGrid) -> RawTable:
    rows = grid.rows
    width = max((len(r.cells) for r in rows), default=0)
    for row in rows:  # pad ragged rows so column positions are stable
        if len(row.cells) < width:
            row.cells.extend([None] * (width - len(row.cells)))
            if row.native is not None:
                row.native.extend([None] * (width - len(row.native)))

    candidates = [r for r in rows[:HEADER_SCAN_ROWS] if not r.is_empty()]
    best: RawRow | None = None
    best_score, best_hits, best_textual = 0.0, 0, False
    for row in candidates:
        score, hits, textual = _header_score(row, width)
        if score > best_score:
            best, best_score, best_hits, best_textual = row, score, hits, textual

    # Without vocabulary hits, accept an all-text row only if values start right below it;
    # otherwise the "best" row is just the first data row of a headerless file.
    has_header = best is not None and (
        best_hits >= 1 or (best_textual and _next_row_has_values(rows, best))
    )
    skipped: list[SkippedRow] = []
    header_row: RawRow | None = best if has_header else None

    used_cols = [c for c in range(width) if any(_has_value(r.cells[c]) for r in rows)]

    if header_row is not None:
        headers = [collapse_ws(header_row.cells[c] or "") for c in used_cols]
        header_key = [normalize_header(h) for h in headers]
        start = rows.index(header_row) + 1
        skipped.extend(SkippedRow(r.index, "title") for r in rows[: start - 1] if not r.is_empty())
    else:
        headers = []
        header_key = []
        start = 0

    data: list[RawRow] = []
    for row in rows[start:]:
        if row.is_empty():
            skipped.append(SkippedRow(row.index, "empty"))
        elif header_key and [normalize_header(row.cells[c] or "") for c in used_cols] == header_key:
            skipped.append(SkippedRow(row.index, "repeated_header"))
        elif _is_total_row(row):
            skipped.append(SkippedRow(row.index, "total"))
        else:
            data.append(row)

    headers = [h or f"#{pos + 1}" for pos, h in enumerate(headers)] or [
        f"#{pos + 1}" for pos in range(len(used_cols))
    ]
    return RawTable(
        sheet=grid.sheet,
        header_row=header_row.index if header_row else None,
        headers=headers,
        col_indexes=used_cols,
        rows=data,
        skipped=sorted(skipped, key=lambda s: s.index),
        meta=dict(grid.meta),
    )
