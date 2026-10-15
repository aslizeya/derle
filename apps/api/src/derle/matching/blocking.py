"""Blocking: only compare profiles that share a cheap key.

Keys are 3-letter prefixes of every token (so "a yilmaz" meets "ahmet yilmaz" through
"yil") plus the phone number. This turns O(n²) comparisons into a small fraction while
keeping every pair the scorer could plausibly accept.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from derle.matching.profiles import Profile

PREFIX = 3
# A block this large means a very common token ("mehmet"). Comparing all of it is still
# cheap at ledger scale; the cap only guards against pathological inputs.
MAX_BLOCK = 2_000


def block_keys(profile: Profile) -> set[str]:
    keys = {f"t:{token[:PREFIX]}" for token in profile.tokens if len(token) > 1}
    if profile.phone:
        keys.add(f"p:{profile.phone}")
    return keys


def candidate_pairs(profiles: list[Profile]) -> set[tuple[int, int]]:
    """Index pairs ``(i, j)`` with ``i < j`` into ``profiles``."""
    blocks: dict[str, list[int]] = defaultdict(list)
    for index, profile in enumerate(profiles):
        for key in block_keys(profile):
            blocks[key].append(index)
    pairs: set[tuple[int, int]] = set()
    for members in blocks.values():
        if len(members) > MAX_BLOCK:
            continue
        pairs.update(combinations(members, 2))
    return pairs
