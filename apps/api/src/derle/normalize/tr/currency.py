"""Currency marker detection: "1.250 TL", "₺1.250", "1250 lira", "USD 40"."""

from __future__ import annotations

import re

from derle.normalize.tr.text import collapse_ws, fold

# Longest tokens first so "ytl" wins over "tl".
_CURRENCY_TOKENS: list[tuple[str, str]] = [
    ("turk lirasi", "TRY"),
    ("lira", "TRY"),
    ("ytl", "TRY"),
    ("try", "TRY"),
    ("tl", "TRY"),
    ("₺", "TRY"),
    ("dolar", "USD"),
    ("usd", "USD"),
    ("$", "USD"),
    ("euro", "EUR"),
    ("avro", "EUR"),
    ("eur", "EUR"),
    ("€", "EUR"),
    ("sterlin", "GBP"),
    ("gbp", "GBP"),
    ("£", "GBP"),
]

_PATTERN = re.compile(
    "|".join(
        rf"(?<![a-z]){re.escape(token)}(?![a-z])" if token[0].isalpha() else re.escape(token)
        for token, _ in _CURRENCY_TOKENS
    )
)
_CODE_BY_TOKEN = dict(_CURRENCY_TOKENS)


def extract_currency(text: str) -> tuple[str, str | None]:
    """Return ``(text_without_currency, ISO code or None)``.

    Matching runs on folded text so "Lira", "LİRA" and "lira" are all recognized.
    """
    source = collapse_ws(text)
    folded = fold(source)
    match = _PATTERN.search(folded)
    if match is None:
        return source, None
    # Folding keeps length for Turkish letters; if some exotic character changed it, slice the
    # folded string instead so positions stay consistent.
    base = source if len(folded) == len(source) else folded
    stripped = (base[: match.start()] + " " + base[match.end() :]).strip()
    return stripped.rstrip(" ."), _CODE_BY_TOKEN[match.group(0)]
