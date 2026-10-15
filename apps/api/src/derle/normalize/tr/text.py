"""Turkish-aware casing, folding and whitespace handling.

Python's default casing is wrong for Turkish: ``"I".lower() == "i"`` (should be ``"ı"``) and
``"İ".lower()`` yields ``"i̇"`` (i + combining dot). Everything here maps the dotted/dotless
pairs explicitly before delegating to ``str.lower``/``str.upper``.
"""

from __future__ import annotations

import re
import unicodedata

_TO_LOWER = str.maketrans({"I": "ı", "İ": "i"})
_TO_UPPER = str.maketrans({"i": "İ", "ı": "I"})
_FOLD = str.maketrans(
    {"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"}
)
_WS = re.compile(r"\s+")
_WORD_START = re.compile(r"(^|[\s\-/(])(\w)")


def collapse_ws(text: str) -> str:
    """Trim and collapse any run of whitespace (including NBSP) into a single space."""
    return _WS.sub(" ", text.replace(" ", " ")).strip()


def tr_lower(text: str) -> str:
    return unicodedata.normalize("NFC", text).translate(_TO_LOWER).lower()


def tr_upper(text: str) -> str:
    return unicodedata.normalize("NFC", text).translate(_TO_UPPER).upper()


def tr_title(text: str) -> str:
    """Title-case words the Turkish way. Text after an apostrophe stays lower ("Ali'nin")."""
    lowered = tr_lower(collapse_ws(text))
    return _WORD_START.sub(lambda m: m.group(1) + tr_upper(m.group(2)), lowered)


def fold(text: str) -> str:
    """Lower-case and strip Turkish diacritics for comparison keys: "Şükrü IŞIK" -> "sukru isik"."""
    lowered = tr_lower(collapse_ws(text)).translate(_FOLD)
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))
