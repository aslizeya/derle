"""Turkish national ID (T.C. Kimlik No) validation and masking."""

from __future__ import annotations

import re


def clean_tckn(text: str) -> str | None:
    digits = re.sub(r"\D", "", text)
    return digits if is_valid_tckn(digits) else None


def is_valid_tckn(digits: str) -> bool:
    if len(digits) != 11 or not digits.isdigit() or digits[0] == "0":
        return False
    d = [int(c) for c in digits]
    odd = d[0] + d[2] + d[4] + d[6] + d[8]
    even = d[1] + d[3] + d[5] + d[7]
    return (odd * 7 - even) % 10 == d[9] and sum(d[:10]) % 10 == d[10]


def mask_tckn(digits: str) -> str:
    return digits[:3] + "*" * 6 + digits[-2:] if len(digits) == 11 else "*" * len(digits)
