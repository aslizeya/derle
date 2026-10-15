"""Date parsing for the formats small businesses actually type.

Handles "15 Mart 2026", "15 mar", "15.03.26", "15/3", "2026-03-15", "Pazartesi 15 Mart",
Excel-style "15.03.2026 14:30" and folded spellings ("15 subat"). Day-first is the Turkish
default; a column-level :class:`DateOrder` can override it when sibling values prove the
order (e.g. "03/25/2026" can only be month-first).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from derle.normalize.tr.text import fold


class DateOrder(StrEnum):
    DMY = "dmy"
    MDY = "mdy"


@dataclass(frozen=True, slots=True)
class DateContext:
    default_year: int | None = None
    order: DateOrder = DateOrder.DMY


@dataclass(frozen=True, slots=True)
class ParsedDate:
    value: date
    ambiguous: bool = False  # day/month could be swapped
    year_inferred: bool = False
    proves_order: DateOrder | None = None


_MONTHS: dict[str, int] = {}
for _num, _names in enumerate(
    [
        ("ocak", "oca", "january", "jan"),
        ("subat", "sub", "february", "feb"),
        ("mart", "mar", "march"),
        ("nisan", "nis", "april", "apr"),
        ("mayis", "may"),
        ("haziran", "haz", "june", "jun"),
        ("temmuz", "tem", "july", "jul"),
        ("agustos", "agu", "aug", "august"),
        ("eylul", "eyl", "september", "sep", "sept"),
        ("ekim", "eki", "october", "oct"),
        ("kasim", "kas", "november", "nov"),
        ("aralik", "ara", "december", "dec"),
    ],
    start=1,
):
    for _name in _names:
        _MONTHS[_name] = _num

_WEEKDAYS = (
    "pazartesi|sali|carsamba|persembe|cuma|cumartesi|pazar|"
    "pzt|sal|car|per|cum|cmt|paz|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
)
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

_TIME_SUFFIX = re.compile(r"[ t]\d{1,2}[:.]\d{2}(?:[:.]\d{2}(?:\.\d+)?)?(?:\s*[ap]m)?$")
_WEEKDAY = re.compile(rf"^(?:{_WEEKDAYS})\b[\s,]*|[\s,]*\b(?:{_WEEKDAYS})$")
_ISO = re.compile(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$")
_NUMERIC = re.compile(r"^(\d{1,2})[./\-](\d{1,2})(?:[./\-](\d{2}|\d{4}))?$")
_COMPACT = re.compile(r"^(\d{2})(\d{2})(\d{4})$")  # 15032026
_TEXTUAL_DMY = re.compile(
    rf"^(\d{{1,2}})\.?[\s\-/.]*({_MONTH_ALT})\.?(?:[\s\-/.,]+(\d{{2}}|\d{{4}}))?$"
)
_TEXTUAL_MDY = re.compile(rf"^({_MONTH_ALT})\.?[\s\-/.]+(\d{{1,2}})(?:[\s,\-/.]+(\d{{4}}))?$")
_APOSTROPHE_SUFFIX = re.compile(r"['’]\w+$")


def parse_date(text: str, ctx: DateContext | None = None) -> ParsedDate | None:
    ctx = ctx or DateContext()
    s = fold(text)
    s = _APOSTROPHE_SUFFIX.sub("", s)  # "15 mart'ta" -> "15 mart"
    s = _TIME_SUFFIX.sub("", s).strip()
    s = _WEEKDAY.sub("", s).strip(" ,")
    if not s:
        return None

    if m := _ISO.match(s):
        return _build(int(m[1]), int(m[2]), int(m[3]))

    if m := _COMPACT.match(s):
        return _build(int(m[3]), int(m[2]), int(m[1]))

    if m := _NUMERIC.match(s):
        a, b = int(m[1]), int(m[2])
        year, inferred = _resolve_year(m[3], ctx)
        if year is None:
            return None
        if a > 12 >= b:
            return _build(year, b, a, year_inferred=inferred, proves=DateOrder.DMY)
        if b > 12 >= a:
            return _build(year, a, b, year_inferred=inferred, proves=DateOrder.MDY)
        day, month = (a, b) if ctx.order == DateOrder.DMY else (b, a)
        return _build(year, month, day, year_inferred=inferred, ambiguous=a != b)

    if m := _TEXTUAL_DMY.match(s):
        year, inferred = _resolve_year(m[3], ctx)
        if year is None:
            return None
        return _build(year, _MONTHS[m[2]], int(m[1]), year_inferred=inferred)

    if m := _TEXTUAL_MDY.match(s):
        year, inferred = _resolve_year(m[3], ctx)
        if year is None:
            return None
        return _build(year, _MONTHS[m[1]], int(m[2]), year_inferred=inferred)

    return None


def _resolve_year(raw: str | None, ctx: DateContext) -> tuple[int | None, bool]:
    if raw is None:
        return ctx.default_year, True
    year = int(raw)
    if len(raw) == 2:
        year += 2000 if year < 70 else 1900
    return year, False


def _build(
    year: int,
    month: int,
    day: int,
    *,
    year_inferred: bool = False,
    ambiguous: bool = False,
    proves: DateOrder | None = None,
) -> ParsedDate | None:
    if not 1900 <= year <= 2100:
        return None
    try:
        value = date(year, month, day)
    except ValueError:
        return None
    return ParsedDate(value, ambiguous=ambiguous, year_inferred=year_inferred, proves_order=proves)


def infer_date_order(values: Iterable[str]) -> DateOrder:
    """Pick DMY unless sibling values prove month-first more often."""
    votes = {DateOrder.DMY: 0, DateOrder.MDY: 0}
    for value in values:
        parsed = parse_date(value, DateContext(default_year=2000))
        if parsed is not None and parsed.proves_order is not None:
            votes[parsed.proves_order] += 1
    return DateOrder.MDY if votes[DateOrder.MDY] > votes[DateOrder.DMY] else DateOrder.DMY


_FILENAME_YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def year_from_filename(filename: str) -> int | None:
    """ "veresiye_mart_2026.xlsx" -> 2026."""
    m = _FILENAME_YEAR.search(filename)
    return int(m[1]) if m else None
