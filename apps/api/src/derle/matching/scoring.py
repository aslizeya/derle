"""Explainable pair scoring.

The score is a logistic function of additive evidence, so every card can say exactly why
it was proposed: "İsim benzerliği %92 (+1.8), aynı telefon (+3.0)". Weights are set by hand
from the benchmark and documented here instead of hidden in a trained model. With only a
few hundred customers per business, a transparent model beats a slightly better opaque one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from rapidfuzz import fuzz
from rapidfuzz.distance import OSA

from derle.matching.profiles import Profile

# Name similarity is centred on 0.8: above it pushes towards "same", below towards "different".
NAME_CENTER = 0.8
NAME_SLOPE = 15.0
PHONE_MATCH = 3.0
PHONE_CONFLICT = -4.0
SURNAME_CONFLICT = -3.0
FIRST_NAME_CONFLICT = -3.0
# Partial names are weaker than a full fuzzy match but should still reach the review queue.
INITIALS_SIMILARITY = 0.85
FIRST_NAME_ONLY_SIMILARITY = 0.82
# One slip of the pen ("Yılmz", "Demri", "Kyaa") is almost always the same person. A changed
# letter in a short word is not: "Kaya" and "Kara" are different families.
TYPO_SIMILARITY = 0.96
TYPO_MIN_LENGTH = 5
# Partial names that point to exactly one known customer (see resolve.py).
UNIQUE_COMPLETION = 2.5

PARTIAL_KINDS = frozenset({"initials_match", "first_name_only"})

AUTO_MERGE = 0.90
REVIEW = 0.50


@dataclass(frozen=True, slots=True)
class Evidence:
    code: str
    weight: float
    value: float | str | None = None


@dataclass(frozen=True, slots=True)
class MatchScore:
    score: float
    evidence: tuple[Evidence, ...] = field(default=())

    @property
    def band(self) -> str:
        if self.score >= AUTO_MERGE:
            return "auto"
        if self.score >= REVIEW:
            return "review"
        return "different"


def _initials_compatible(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """ "a yilmaz" ~ "ahmet yilmaz": same length, each token equal or an initial of the other,
    at least one full token shared and at least one initial used."""
    if len(a) != len(b) or len(a) < 2:
        return False
    used_initial = shared_full = False
    for x, y in zip(a, b, strict=True):
        if x == y:
            shared_full = shared_full or len(x) > 1
        elif (len(x) == 1 and y.startswith(x)) or (len(y) == 1 and x.startswith(y)):
            used_initial = True
        else:
            return False
    return used_initial and shared_full


def _first_name_only(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """ "ahmet" vs "ahmet yilmaz": the shorter name is a strict prefix of the longer one."""
    short, long = (a, b) if len(a) < len(b) else (b, a)
    return 0 < len(short) < len(long) and long[: len(short)] == short and len(short[0]) > 1


def _single_typo(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """Same tokens except one that differs by a single slip: two swapped neighbours, one
    dropped letter (in a word of 5+ letters) or one substituted letter (5+ letters)."""
    if len(a) != len(b):
        return False
    diffs = [(x, y) for x, y in zip(a, b, strict=True) if x != y]
    if len(diffs) != 1:
        return False
    x, y = diffs[0]
    if OSA.distance(x, y) != 1:
        return False
    if len(x) == len(y) and sorted(x) == sorted(y):
        return len(x) >= 4  # swapped neighbours: "kaya" -> "kyaa"
    if len(x) != len(y):
        return max(len(x), len(y)) >= TYPO_MIN_LENGTH  # dropped letter: "bulut" -> "bult"
    return len(x) >= TYPO_MIN_LENGTH  # substituted letter: only in long words (Kaya ≠ Kara)


def _first_name_conflict(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """ "s kara" vs "z kara", "ahmet" vs "mehmet": first names that cannot be the same."""
    if len(a) < 2 or len(b) < 2 or a[0] == b[0]:
        return False
    x, y = a[0], b[0]
    if len(x) == 1 or len(y) == 1:
        return not (y.startswith(x) or x.startswith(y))
    # More than one keystroke apart: "ahmet" / "mehmet" are different names, "mehmt" is a slip.
    return OSA.distance(x, y) > 1


def _surname_conflict(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    if len(a) < 2 or len(b) < 2:
        return False
    last_a, last_b = a[-1], b[-1]
    if len(last_a) == 1 or len(last_b) == 1:
        return False
    return fuzz.ratio(last_a, last_b) < 70


def score_pair(a: Profile, b: Profile) -> MatchScore:
    evidence: list[Evidence] = []

    if a.key == b.key:
        similarity = 1.0
        evidence.append(Evidence("name_exact", 0.0, 1.0))
    else:
        similarity = fuzz.token_sort_ratio(a.key, b.key) / 100
        code = "name_similarity"
        if _initials_compatible(a.tokens, b.tokens):
            similarity, code = max(similarity, INITIALS_SIMILARITY), "initials_match"
        elif _first_name_only(a.tokens, b.tokens):
            similarity, code = max(similarity, FIRST_NAME_ONLY_SIMILARITY), "first_name_only"
        elif _single_typo(a.tokens, b.tokens):
            similarity, code = max(similarity, TYPO_SIMILARITY), "typo"
        evidence.append(Evidence(code, 0.0, round(similarity, 3)))

    logit = NAME_SLOPE * (similarity - NAME_CENTER)
    evidence[0] = Evidence(evidence[0].code, round(logit, 2), evidence[0].value)

    if a.phone and b.phone:
        if a.phone == b.phone:
            logit += PHONE_MATCH
            evidence.append(Evidence("phone_match", PHONE_MATCH))
        else:
            logit += PHONE_CONFLICT
            evidence.append(Evidence("phone_conflict", PHONE_CONFLICT))

    if _surname_conflict(a.tokens, b.tokens):
        logit += SURNAME_CONFLICT
        evidence.append(Evidence("surname_conflict", SURNAME_CONFLICT))

    if _first_name_conflict(a.tokens, b.tokens):
        logit += FIRST_NAME_CONFLICT
        evidence.append(Evidence("first_name_conflict", FIRST_NAME_CONFLICT))

    return MatchScore(score=_sigmoid(logit), evidence=tuple(evidence))


def _sigmoid(logit: float) -> float:
    return round(1 / (1 + math.exp(-logit)), 4)


def with_unique_completion(match: MatchScore) -> MatchScore:
    """Add the context bonus for a partial name that has exactly one plausible owner."""
    logit = sum(e.weight for e in match.evidence) + UNIQUE_COMPLETION
    evidence = (*match.evidence, Evidence("unique_completion", UNIQUE_COMPLETION))
    return MatchScore(score=_sigmoid(logit), evidence=evidence)


def is_partial(match: MatchScore) -> bool:
    return bool(match.evidence) and match.evidence[0].code in PARTIAL_KINDS
