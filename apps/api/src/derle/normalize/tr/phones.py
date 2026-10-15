"""Turkish phone numbers: "0532 123 45 67", "+90 (532) 123-4567", "5321234567" -> +905321234567."""

from __future__ import annotations

import re
from dataclasses import dataclass

_CANDIDATE = re.compile(r"\+?[\d\s().\-/]{10,}")
_VALID_AREA_FIRST_DIGIT = frozenset("23458")


@dataclass(frozen=True, slots=True)
class ParsedPhone:
    e164: str  # +905321234567
    national: str  # 0532 123 45 67
    is_mobile: bool


def parse_phone(text: str) -> ParsedPhone | None:
    for candidate in _CANDIDATE.findall(text):
        parsed = _parse_digits(re.sub(r"\D", "", candidate))
        if parsed is not None:
            return parsed
    return None


def _parse_digits(digits: str) -> ParsedPhone | None:
    if digits.startswith("0090"):
        digits = digits[4:]
    elif len(digits) == 12 and digits.startswith("90"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in _VALID_AREA_FIRST_DIGIT:
        return None
    national = f"0{digits[:3]} {digits[3:6]} {digits[6:8]} {digits[8:]}"
    return ParsedPhone(e164=f"+90{digits}", national=national, is_mobile=digits[0] == "5")


def mask_phone(national: str) -> str:
    """ "0532 123 45 67" -> "0532 *** ** 67"."""
    parts = national.split(" ")
    if len(parts) != 4:
        return "*" * max(len(national) - 2, 0) + national[-2:]
    return f"{parts[0]} *** ** {parts[3]}"
