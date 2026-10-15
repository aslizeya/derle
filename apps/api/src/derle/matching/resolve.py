"""Constrained clustering of profiles into entities.

1. Must-link decisions ("aynı") are merged first, unconditionally.
2. Auto-merge pairs are merged in descending score order, unless the merge would put two
   profiles the user said are different into one cluster (cannot-link).
3. Review-band pairs that still connect different clusters become question cards, at most
   one per cluster pair (the strongest one).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from derle.matching.blocking import candidate_pairs
from derle.matching.profiles import Profile
from derle.matching.scoring import (
    AUTO_MERGE,
    REVIEW,
    MatchScore,
    is_partial,
    score_pair,
    with_unique_completion,
)


@dataclass(frozen=True, slots=True)
class Decision:
    profile_a: str
    profile_b: str
    decision: str  # same | different | skip


@dataclass(frozen=True, slots=True)
class ReviewPair:
    a: int  # index into profiles
    b: int
    match: MatchScore


@dataclass(slots=True)
class Resolution:
    clusters: list[list[int]]
    review: list[ReviewPair]
    auto_merges: int = 0
    comparisons: int = 0
    blocked_by_decision: int = 0
    cluster_of: dict[int, int] = field(default_factory=dict)  # profile index -> cluster index


def pair_key(a: str, b: str) -> str:
    return "||".join(sorted((a, b)))


class _ConstrainedUnionFind:
    def __init__(self, n: int, cannot: dict[int, set[int]]) -> None:
        self.parent = list(range(n))
        self.members: dict[int, set[int]] = {i: {i} for i in range(n)}
        self.forbidden: dict[int, set[int]] = {i: set(cannot.get(i, ())) for i in range(n)}

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def can_merge(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        return ra == rb or not (self.forbidden[ra] & self.members[rb])

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.forbidden[ra] & self.members[rb]:
            return False
        if len(self.members[ra]) < len(self.members[rb]):
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.members[ra] |= self.members.pop(rb)
        self.forbidden[ra] |= self.forbidden.pop(rb)
        return True


def _is_complete(p: Profile) -> bool:
    return len(p.tokens) >= 2 and all(len(t) > 1 for t in p.tokens)


def _anchored(profiles: list[Profile], uf: _ConstrainedUnionFind, i: int, j: int) -> bool:
    """The partial side of a pair already belongs to a full name ("M. Yılmaz" was confirmed
    as Mehmet Yılmaz), so asking about it again would really ask "Mehmet = Murat?"."""
    partial = i if len(profiles[i].key) < len(profiles[j].key) else j
    root = uf.find(partial)
    return any(_is_complete(profiles[m]) for m in uf.members[root])


def _merge_unique_completions(
    profiles: list[Profile],
    scored: list[tuple[int, int, MatchScore]],
    uf: _ConstrainedUnionFind,
) -> int:
    """Phase 2: a partial name ("m yilmaz", "elif") joins its owner when exactly one cluster
    could own it. With two candidates ("Mehmet Yılmaz" and "Murat Yılmaz") it stays a question.

    Clustering is recomputed from scratch on every run, so a merge made while only one
    "Mehmet" existed is reconsidered automatically when a second one shows up.
    """
    links: dict[int, list[tuple[int, MatchScore]]] = defaultdict(list)
    for i, j, match in scored:
        if match.score < REVIEW or not is_partial(match):
            continue
        partial, owner = (i, j) if len(profiles[i].key) < len(profiles[j].key) else (j, i)
        links[partial].append((owner, match))

    merged = 0
    for partial in sorted(links, key=lambda k: profiles[k].id):
        root = uf.find(partial)
        if any(_is_complete(profiles[m]) for m in uf.members[root]):
            continue  # already anchored to a full name (e.g. by a user decision)
        owners: dict[int, tuple[int, MatchScore]] = {}
        for owner, match in links[partial]:
            owner_root = uf.find(owner)
            if owner_root == root or not uf.can_merge(partial, owner):
                continue
            if owner_root not in owners or match.score > owners[owner_root][1].score:
                owners[owner_root] = (owner, match)
        if len(owners) != 1:
            continue
        owner, match = next(iter(owners.values()))
        if with_unique_completion(match).score >= AUTO_MERGE and uf.union(partial, owner):
            merged += 1
    return merged


def resolve(profiles: list[Profile], decisions: list[Decision] | None = None) -> Resolution:
    decisions = decisions or []
    index = {p.id: i for i, p in enumerate(profiles)}

    must: list[tuple[int, int]] = []
    cannot: dict[int, set[int]] = {}
    decided: set[str] = set()
    for d in decisions:
        decided.add(pair_key(d.profile_a, d.profile_b))
        if d.profile_a not in index or d.profile_b not in index:
            continue  # the records behind this decision are gone (e.g. upload undone)
        a, b = index[d.profile_a], index[d.profile_b]
        if d.decision == "same":
            must.append((a, b))
        elif d.decision == "different":
            cannot.setdefault(a, set()).add(b)
            cannot.setdefault(b, set()).add(a)

    pairs = candidate_pairs(profiles)
    scored = [(i, j, score_pair(profiles[i], profiles[j])) for i, j in sorted(pairs)]

    uf = _ConstrainedUnionFind(len(profiles), cannot)
    for a, b in must:
        uf.union(a, b)

    result = Resolution(clusters=[], review=[], comparisons=len(scored))
    for i, j, match in sorted(scored, key=lambda t: -t[2].score):
        if match.score < AUTO_MERGE:
            break
        if uf.union(i, j):
            result.auto_merges += 1
        elif uf.find(i) != uf.find(j):
            result.blocked_by_decision += 1

    result.auto_merges += _merge_unique_completions(profiles, scored, uf)

    roots: dict[int, int] = {}
    for i in range(len(profiles)):
        root = uf.find(i)
        if root not in roots:
            roots[root] = len(result.clusters)
            result.clusters.append([])
        result.clusters[roots[root]].append(i)
        result.cluster_of[i] = roots[root]

    best: dict[tuple[int, int], ReviewPair] = {}
    for i, j, match in scored:
        if match.score < REVIEW:
            continue
        ci, cj = result.cluster_of[i], result.cluster_of[j]
        if ci == cj or not uf.can_merge(i, j):
            continue
        if pair_key(profiles[i].id, profiles[j].id) in decided:
            continue
        if is_partial(match) and _anchored(profiles, uf, i, j):
            continue
        key = (min(ci, cj), max(ci, cj))
        if key not in best or match.score > best[key].match.score:
            best[key] = ReviewPair(i, j, match)
    result.review = sorted(best.values(), key=lambda r: -r.match.score)
    return result
