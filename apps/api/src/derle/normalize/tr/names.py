"""Person and company name normalization.

"ahmet bey", "AHMET YILMAZ (manav)", "Yılmaz, Ahmet", "Sn. Dr. Ayşe Kaya" all become a clean
display form plus a folded comparison key. Removed honorifics and notes are reported so the
UI can explain the change and the matcher can still use them as weak signals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from derle.normalize.tr.text import collapse_ws, fold, tr_title, tr_upper

# Folded forms. Suffix honorifics follow the name ("Ahmet bey"); prefix titles precede it.
HONORIFIC_SUFFIXES = frozenset(
    {
        "bey", "beyefendi", "hanim", "hanimefendi", "abi", "agabey", "abla", "amca", "teyze",
        "dayi", "usta", "hoca", "hocam", "efendi", "kardes", "eniste", "yenge",
    }
)  # fmt: skip
PREFIX_TITLES = frozenset(
    {"bay", "bayan", "sayin", "sn", "dr", "av", "prof", "doc", "uzm", "muh", "ecz", "op"}
)
COMPANY_MARKERS = frozenset(
    {"ltd", "sti", "a.s", "as", "san", "tic", "ltd.sti", "holding", "insaat", "gida", "koop"}
)

_PAREN_NOTE = re.compile(r"\s*[(\[]([^)\]]*)[)\]]\s*")
_APOSTROPHE_SUFFIX = re.compile(r"['’][a-zçğıöşü]+$", re.IGNORECASE)
_INITIAL = re.compile(r"^[a-zçğıöşü]\.?$", re.IGNORECASE)
_NON_NAME = re.compile(r"[^\w\s.'’&\-]")


@dataclass(frozen=True, slots=True)
class ParsedName:
    display: str  # "Ahmet Yılmaz"
    key: str  # "ahmet yilmaz"
    honorifics: tuple[str, ...] = ()
    note: str | None = None  # "(manav)" -> "manav"
    has_initials: bool = False
    is_company: bool = False
    reordered: bool = False  # "Yılmaz, Ahmet" was flipped
    tokens: tuple[str, ...] = field(default=())


def parse_name(text: str) -> ParsedName | None:
    s = collapse_ws(text)
    if not s:
        return None

    note = None
    notes = _PAREN_NOTE.findall(s)
    if notes:
        note = collapse_ws(" ".join(notes)) or None
        s = collapse_ws(_PAREN_NOTE.sub(" ", s))

    reordered = False
    if s.count(",") == 1:
        last, first = (part.strip() for part in s.split(","))
        if first and last and " " not in last:
            s, reordered = f"{first} {last}", True

    s = collapse_ws(_NON_NAME.sub(" ", s))
    raw_tokens = [_APOSTROPHE_SUFFIX.sub("", t) for t in s.split(" ") if t]
    folded = [fold(t).rstrip(".") for t in raw_tokens]

    is_company = any(f in COMPANY_MARKERS for f in folded)
    honorifics: list[str] = []
    kept: list[str] = []
    for i, (token, key) in enumerate(zip(raw_tokens, folded, strict=True)):
        if not is_company and key in PREFIX_TITLES and i < len(raw_tokens) - 1:
            honorifics.append(key)
            continue
        if not is_company and key in HONORIFIC_SUFFIXES and i > 0:
            honorifics.append(key)
            continue
        kept.append(token)

    if not kept:
        return None

    display_tokens = [_display_token(t) for t in kept]
    display = " ".join(display_tokens)
    key = fold(" ".join(t.rstrip(".") for t in kept))
    return ParsedName(
        display=display,
        key=key,
        honorifics=tuple(honorifics),
        note=note,
        has_initials=any(_INITIAL.match(t) for t in kept),
        is_company=is_company,
        reordered=reordered,
        tokens=tuple(key.split(" ")),
    )


def _display_token(token: str) -> str:
    if _INITIAL.match(token):
        return tr_upper(token[0]) + "."
    return tr_title(token)


def combine_first_last(first: str | None, last: str | None) -> str | None:
    parts = [p.strip() for p in (first, last) if p and p.strip()]
    return " ".join(parts) or None
