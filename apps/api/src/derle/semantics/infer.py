"""Rule-based column role inference.

Each column gets a score per role from two independent signals:

* **header** — vocabulary lookup (:mod:`derle.semantics.dictionary`)
* **values** — what fraction of a sample parses as a date, number, phone, TCKN, e-mail, name

Both are reported as :class:`Reason` objects so the UI can say *why* a column was labelled
"Tarih": e.g. ``header_match{keyword: tarih}`` + ``values_parse{kind: date, ratio: 0.97}``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from derle.domain.models import ColumnInference, ColumnRole, Reason
from derle.ingest.base import RawTable
from derle.normalize.tr.dates import DateContext, parse_date
from derle.normalize.tr.names import parse_name
from derle.normalize.tr.numbers import parse_number
from derle.normalize.tr.phones import parse_phone
from derle.normalize.tr.tckn import clean_tckn
from derle.semantics.dictionary import match_header

SAMPLE_SIZE = 200
HEADER_WEIGHT = 0.6
VALUE_WEIGHT = 0.4
MIN_CONFIDENCE = 0.35

_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
_LETTERS = re.compile(r"^[^\d@]+$")


@dataclass(frozen=True, slots=True)
class ValueProfile:
    n: int
    date: float
    number: float
    integer: float
    currency: float
    phone: float
    tckn: float
    email: float
    name_like: float
    distinct: float  # distinct values / n
    avg_len: float


def profile_values(values: Sequence[str]) -> ValueProfile:
    sample = list(values[:SAMPLE_SIZE])
    n = len(sample)
    if n == 0:
        return ValueProfile(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    ctx = DateContext(default_year=2000)
    dates = numbers = integers = currency = phones = tckns = emails = names = 0
    for value in sample:
        num = parse_number(value)
        tckn = clean_tckn(value) if len(value.strip()) <= 14 else None
        phone = parse_phone(value) if tckn is None else None
        # Pure integers like "2026" or "15" are not dates; dates need separators or month names.
        is_date = parse_date(value, ctx) is not None and not value.strip().isdigit()
        dates += is_date
        if num is not None and not is_date and phone is None and tckn is None:
            numbers += 1
            integers += num.value == num.value.to_integral_value()
            currency += num.currency is not None
        phones += phone is not None
        tckns += tckn is not None
        emails += bool(_EMAIL.match(value.strip()))
        if _LETTERS.match(value) and len(value.split()) <= 5:
            names += parse_name(value) is not None

    distinct = len({v.strip().casefold() for v in sample}) / n
    avg_len = sum(len(v) for v in sample) / n
    return ValueProfile(
        n=n,
        date=dates / n,
        number=numbers / n,
        integer=integers / n,
        currency=currency / n,
        phone=phones / n,
        tckn=tckns / n,
        email=emails / n,
        name_like=names / n,
        distinct=distinct,
        avg_len=avg_len,
    )


def value_scores(p: ValueProfile) -> dict[ColumnRole, float]:
    """How well the values fit each role, independent of the header."""
    if p.n == 0:
        return {}
    money = p.number * (1.0 if p.currency > 0 or p.integer < 0.9 else 0.8)
    short_text = p.name_like * (1.0 if p.avg_len <= 30 else 0.5)
    return {
        ColumnRole.DATE: p.date,
        ColumnRole.AMOUNT: money,
        ColumnRole.DEBIT: money,
        ColumnRole.CREDIT: money,
        ColumnRole.BALANCE: money,
        ColumnRole.QUANTITY: p.number * (1.0 if p.integer > 0.9 and p.currency == 0 else 0.6),
        ColumnRole.PHONE: p.phone,
        ColumnRole.TCKN: p.tckn,
        ColumnRole.EMAIL: p.email,
        # Names repeat (same customer, many rows); free text rarely does.
        ColumnRole.PARTY: short_text * (1.0 if p.distinct < 0.9 else 0.7),
        ColumnRole.FIRST_NAME: short_text * 0.9,
        ColumnRole.LAST_NAME: short_text * 0.9,
        ColumnRole.DESCRIPTION: (1 - p.number) * (1 - p.date) * 0.7,
        ColumnRole.CATEGORY: (1 - p.number) * (0.8 if p.distinct < 0.3 else 0.2),
        ColumnRole.IDENTIFIER: p.integer * (1.0 if p.distinct > 0.95 else 0.3),
    }


def _value_only_role(p: ValueProfile) -> tuple[ColumnRole, float, str]:
    """Best guess when the header tells us nothing (or there is no header)."""
    if p.phone >= 0.8:
        return ColumnRole.PHONE, p.phone, "phone"
    if p.tckn >= 0.8:
        return ColumnRole.TCKN, p.tckn, "tckn"
    if p.email >= 0.8:
        return ColumnRole.EMAIL, p.email, "email"
    if p.date >= 0.7:
        return ColumnRole.DATE, p.date, "date"
    if p.number >= 0.7:
        if p.integer > 0.95 and p.distinct > 0.95 and p.currency == 0:
            return ColumnRole.IDENTIFIER, p.number * 0.6, "number"
        return ColumnRole.AMOUNT, p.number * 0.8, "number"
    if p.name_like >= 0.7 and p.avg_len <= 30 and p.distinct < 0.9:
        return ColumnRole.PARTY, p.name_like * 0.7, "name"
    return ColumnRole.DESCRIPTION, 0.4, "text"


def infer_column(col_index: int, header: str, values: Sequence[str]) -> ColumnInference:
    profile = profile_values(values)
    fits = value_scores(profile)
    reasons: list[Reason] = []

    header_hit = match_header(header)
    if header_hit is not None:
        role, strength, keyword = header_hit
        reasons.append(Reason(code="header_match", params={"keyword": keyword, "role": role}))
        fit = fits.get(role, 0.0) if profile.n else 0.5
        confidence = HEADER_WEIGHT * strength + VALUE_WEIGHT * fit
        if profile.n:
            reasons.append(Reason(code="values_fit", params={"role": role, "ratio": round(fit, 2)}))
        # Values strongly contradict the header ("Tutar" full of dates): trust the values.
        alt_role, alt_conf, kind = _value_only_role(profile)
        if profile.n >= 3 and fit < 0.3 and alt_conf >= 0.7 and alt_role != role:
            reasons.append(Reason(code="values_override", params={"kind": kind}))
            return ColumnInference(
                col_index=col_index,
                header=header,
                role=alt_role,
                confidence=round(alt_conf * 0.8, 3),
                reasons=reasons,
            )
        return ColumnInference(
            col_index=col_index,
            header=header,
            role=role,
            confidence=round(min(confidence, 1.0), 3),
            reasons=reasons,
        )

    role, confidence, kind = _value_only_role(profile)
    reasons.append(
        Reason(code="values_parse", params={"kind": kind, "ratio": round(confidence, 2)})
    )
    if confidence < MIN_CONFIDENCE:
        role = ColumnRole.UNKNOWN
    return ColumnInference(
        col_index=col_index,
        header=header,
        role=role,
        confidence=round(confidence, 3),
        reasons=reasons,
    )


def infer_table(table: RawTable) -> list[ColumnInference]:
    inferences = [
        infer_column(table.col_indexes[pos], header, table.column_values(pos))
        for pos, header in enumerate(table.headers)
    ]
    return resolve_conflicts(inferences)


def resolve_conflicts(inferences: list[ColumnInference]) -> list[ColumnInference]:
    """Enforce one-per-table roles: keep the most confident PARTY/PHONE/TCKN/EMAIL column and
    demote the others to DESCRIPTION. Split first/last name columns are left for the
    normalizer to combine."""
    singular = {ColumnRole.PARTY, ColumnRole.PHONE, ColumnRole.TCKN, ColumnRole.EMAIL}
    has_split_name = any(i.role == ColumnRole.FIRST_NAME for i in inferences) and any(
        i.role == ColumnRole.LAST_NAME for i in inferences
    )
    out: list[ColumnInference] = []
    winners: dict[ColumnRole, ColumnInference] = {}
    for inf in inferences:
        if inf.role in singular:
            current = winners.get(inf.role)
            if current is None or inf.confidence > current.confidence:
                winners[inf.role] = inf
    for inf in inferences:
        demote = inf.role in singular and winners.get(inf.role) is not inf
        if inf.role == ColumnRole.PARTY and has_split_name:
            demote = True
        if not demote:
            out.append(inf)
            continue
        out.append(
            inf.model_copy(
                update={
                    "role": ColumnRole.DESCRIPTION,
                    "reasons": [*inf.reasons, Reason(code="demoted_duplicate_role")],
                }
            )
        )
    return out


__all__ = ["MIN_CONFIDENCE", "infer_column", "infer_table", "profile_values"]
