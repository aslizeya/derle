"""Number parsing for Turkish and international formats.

Turkish writes ``1.234,56`` (dot = thousands, comma = decimal); spreadsheets exported from
English-locale software write ``1,234.56``. Single-separator values such as ``1.234`` are
genuinely ambiguous, so the parser reports ambiguity and accepts a column-level ``style``
hint inferred from sibling values (see :func:`infer_number_style`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from derle.normalize.tr.currency import extract_currency
from derle.normalize.tr.text import fold


class NumberStyle(StrEnum):
    TR = "tr"  # 1.234,56
    EN = "en"  # 1,234.56


@dataclass(frozen=True, slots=True)
class ParsedNumber:
    value: Decimal
    currency: str | None = None
    style: NumberStyle | None = None  # the style this value *proves*, if any
    ambiguous: bool = False


_MULTIPLIERS: dict[str, Decimal] = {
    "bin": Decimal(1_000),
    "milyon": Decimal(1_000_000),
    "milyar": Decimal(1_000_000_000),
}
_MULTIPLIER_RE = re.compile(r"^(?P<num>.*?)\s*(?P<word>bin|milyon|milyar)$")
_NUMERIC_BODY = re.compile(r"^\d[\d.,]*$|^[.,]\d+$")
_INNER_SPACES = re.compile(r"(?<=\d)[\s'’](?=\d{3}\b)")
_MINUS_CHARS = "-−–"


def parse_number(text: str, style: NumberStyle | None = None) -> ParsedNumber | None:
    """Parse ``text`` into a Decimal; return ``None`` when it is not a number."""
    body, currency = extract_currency(text)
    body = body.strip()
    if not body:
        return None

    negative = False
    if body.startswith("(") and body.endswith(")"):
        negative, body = True, body[1:-1].strip()
    if body and body[0] in _MINUS_CHARS:
        negative, body = True, body[1:].strip()
    elif body and body[-1] in _MINUS_CHARS:
        negative, body = True, body[:-1].strip()
    if body.startswith("+"):
        body = body[1:].strip()

    multiplier = Decimal(1)
    word_match = _MULTIPLIER_RE.match(fold(body))
    if word_match:
        multiplier = _MULTIPLIERS[word_match.group("word")]
        body = body[: len(word_match.group("num"))].strip() or "1"

    body = _INNER_SPACES.sub("", body)
    if not _NUMERIC_BODY.match(body):
        return None

    parsed = _parse_separators(body, style)
    if parsed is None:
        return None
    digits, proven_style, ambiguous = parsed
    try:
        value = Decimal(digits) * multiplier
    except InvalidOperation:
        return None
    if negative:
        value = -value
    return ParsedNumber(value=value, currency=currency, style=proven_style, ambiguous=ambiguous)


def _parse_separators(
    body: str, hint: NumberStyle | None
) -> tuple[str, NumberStyle | None, bool] | None:
    """Return ``(canonical_digits, proven_style, ambiguous)``."""
    dots, commas = body.count("."), body.count(",")

    if dots and commas:
        decimal_sep = "," if body.rfind(",") > body.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        if body.count(decimal_sep) > 1:
            return None
        int_part, frac = body.split(decimal_sep)
        if not _valid_grouping(int_part, thousands_sep):
            return None
        style = NumberStyle.TR if decimal_sep == "," else NumberStyle.EN
        return f"{int_part.replace(thousands_sep, '')}.{frac}", style, False

    if not dots and not commas:
        return body, None, False

    sep = "." if dots else ","
    if body.count(sep) > 1:
        # Repeated separator can only be a thousands separator: 1.234.567 or 1,234,567.
        if not _valid_grouping(body, sep):
            return None
        return body.replace(sep, ""), (NumberStyle.TR if sep == "." else NumberStyle.EN), False

    int_part, frac = body.split(sep)
    could_be_thousands = len(frac) == 3 and 1 <= len(int_part) <= 3 and int_part not in {"", "0"}
    if not could_be_thousands:
        style = NumberStyle.TR if sep == "," else NumberStyle.EN
        return f"{int_part or '0'}.{frac}", style, False

    # "1.234" / "1,234": thousands or decimal? Use the column hint, else the Turkish default.
    effective = hint or NumberStyle.TR
    is_thousands = (sep == ".") == (effective == NumberStyle.TR)
    digits = f"{int_part}{frac}" if is_thousands else f"{int_part}.{frac}"
    return digits, None, hint is None


def _valid_grouping(int_part: str, sep: str) -> bool:
    groups = int_part.split(sep)
    if len(groups) == 1:
        return groups[0].isdigit() or groups[0] == ""
    return (
        1 <= len(groups[0]) <= 3
        and groups[0].isdigit()
        and all(len(g) == 3 and g.isdigit() for g in groups[1:])
    )


def infer_number_style(values: Iterable[str]) -> NumberStyle | None:
    """Majority vote over values that unambiguously prove a style. ``None`` if no evidence."""
    votes = {NumberStyle.TR: 0, NumberStyle.EN: 0}
    for value in values:
        parsed = parse_number(value)
        if parsed is not None and parsed.style is not None:
            votes[parsed.style] += 1
    if votes[NumberStyle.TR] == votes[NumberStyle.EN]:
        return None
    return max(votes, key=lambda s: votes[s])


def format_decimal(value: Decimal) -> str:
    """Canonical, locale-free rendering used in transformation logs: ``1234.5``."""
    text = format(value.normalize(), "f")
    return text if "." not in text else text.rstrip("0").rstrip(".")
