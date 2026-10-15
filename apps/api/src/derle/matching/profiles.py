"""Name profiles: the unit of matching.

Many records mention the same written name ("Ahmet Yılmaz" appears 30 times). Matching
works on distinct *profiles* (folded name + phone) instead of records. That keeps the
pairwise work small, and a decision about a profile automatically applies to every
present and future record carrying it.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from derle.normalize.tr.text import fold


@dataclass(frozen=True, slots=True)
class Mention:
    record_id: int
    name: str  # normalized display form, e.g. "A. Yılmaz"
    phone: str | None = None  # any format; reduced to digits


@dataclass(slots=True)
class Profile:
    id: str  # "a yilmaz|5321234567"
    key: str  # "a yilmaz"
    tokens: tuple[str, ...]
    phone: str | None
    names: Counter[str] = field(default_factory=Counter)
    record_ids: list[int] = field(default_factory=list)

    @property
    def display(self) -> str:
        return self.names.most_common(1)[0][0]


def name_key(name: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", fold(name)).split())


def phone_key(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    return digits[-10:] if len(digits) >= 10 else None


def profile_id(key: str, phone: str | None) -> str:
    return f"{key}|{phone or ''}"


def build_profiles(mentions: Iterable[Mention]) -> list[Profile]:
    by_id: dict[str, Profile] = {}
    for m in mentions:
        key = name_key(m.name)
        if not key:
            continue
        phone = phone_key(m.phone)
        pid = profile_id(key, phone)
        profile = by_id.get(pid)
        if profile is None:
            profile = Profile(id=pid, key=key, tokens=tuple(key.split()), phone=phone)
            by_id[pid] = profile
        profile.names[m.name] += 1
        profile.record_ids.append(m.record_id)
    return sorted(by_id.values(), key=lambda p: p.id)
