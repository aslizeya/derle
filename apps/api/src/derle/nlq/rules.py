"""Rule-based Turkish question → SQL for the questions a shopkeeper actually asks.

    "Geçen ay en çok kim borçlandı?"      → sales by customer, last month, top 10
    "Ahmet Yılmaz'ın borcu ne kadar?"     → open balance for one customer
    "Mart'ta ne kadar ödeme alındı?"      → payments in March
    "Hangi ay en çok satış yaptık?"       → sales by month, highest first
    "Kaç müşterim var?"                   → distinct customers

The question is folded (Turkish-aware lower case, no diacritics), matched against small
keyword sets for *metric*, *grouping*, *order*, *period* and *customer*, and turned into a
:class:`Plan`. ``plan_to_sql`` renders it with the dataset's money model, so the SQL shown to
the user is the SQL that ran. Anything outside these patterns returns ``None`` and is left
to the optional LLM path.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from derle.analytics.schema import DatasetSchema
from derle.normalize.tr.text import fold

MONTHS = ["ocak", "subat", "mart", "nisan", "mayis", "haziran", "temmuz", "agustos", "eylul",
          "ekim", "kasim", "aralik"]  # fmt: skip
DEFAULT_TOP = 10

_BALANCE = re.compile(
    r"\b(bakiye\w*|kalan\w*|borcu\b|borclari\w*|borcum\w*|acik hesap\w*|alacagim\w*)"
)
_PAYMENTS = re.compile(r"\b(odeme\w*|odedi\w*|odenen\w*|odeyen\w*|tahsil\w*|yatir\w*)")
_SALES = re.compile(
    r"\b(borclan\w*|veresiye\w*|aldi\w*|alan\b|satis\w*|sattig\w*|ciro\w*|harca\w*|alisveris\w*|tutar\w*|borc\b|borc\w*)"
)
_COUNT_RECORDS = re.compile(r"\b(kac (kayit|islem|satir)|(kayit|islem) sayisi)")
_COUNT_CUSTOMERS = re.compile(r"\b(kac (musteri|kisi)\w*|musteri sayisi)")
_AVERAGE = re.compile(r"\bortalama\w*")
_BY_CUSTOMER = re.compile(
    r"\b(kim|kimin|kimler\w*|hangi musteri\w*|musteri bazinda|musterilere gore|musteriler\w*)\b"
)
_BY_MONTH = re.compile(r"\b(hangi ay\w*|aylik|aylara gore|her ay|ay ay|ay bazinda)\b")
_BY_DAY = re.compile(r"\b(hangi gun\w*|gunluk|gunlere gore|her gun)\b")
_DESC = re.compile(r"\ben (cok|fazla|yuksek|buyuk)\b")
_ASC = re.compile(r"\ben (az|dusuk|kucuk)\b")
_TOP_N = re.compile(r"\b(?:ilk|top)\s*(\d{1,3})\b|\b(\d{1,3})\s*(?:kisi|musteri)\b")
_LAST_N = re.compile(r"\bson (\d{1,3}) (gun|hafta|ay|yil)\w*")
_YEAR = re.compile(r"\b(20\d\d|19\d\d)\b")
_MONTH = re.compile(rf"\b({'|'.join(MONTHS)})\w*")


class PlanError(Exception):
    def __init__(self, code: str, **params: Any) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


@dataclass(slots=True)
class Period:
    start: date
    end: date  # exclusive
    code: str  # last_month, this_year, month, year, last_n, today, …
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Plan:
    metric: str  # sales | payments | balance | count | customers
    aggregate: str = "sum"  # sum | avg | count
    group: str | None = None  # customer | month | day
    order: str | None = None  # desc | asc
    limit: int | None = None
    period: Period | None = None
    customer: tuple[int, str] | None = None


@dataclass(frozen=True, slots=True)
class EntityName:
    id: int
    name: str
    keys: tuple[str, ...]  # folded canonical name and aliases


def normalize_question(question: str) -> str:
    text = question.replace("’", "'")
    text = re.sub(r"'\w*", "", text)  # Ahmet'in → Ahmet, Mart'ta → Mart
    return " ".join(re.sub(r"[^\w\s]", " ", fold(text)).split())


def _month_period(year: int, month: int, code: str = "month") -> Period:
    last = calendar.monthrange(year, month)[1]
    start = date(year, month, 1)
    return Period(start, start + timedelta(days=last), code, {"year": year, "month": month})


def detect_period(q: str, anchor: date) -> Period | None:
    if m := _LAST_N.search(q):
        n, unit = int(m.group(1)), m.group(2)
        days = {"gun": n, "hafta": 7 * n, "ay": 30 * n, "yil": 365 * n}[unit]
        return Period(
            anchor - timedelta(days=days - 1),
            anchor + timedelta(days=1),
            "last_n",
            {"n": n, "unit": unit},
        )
    if re.search(r"\bbugun\w*", q):
        return Period(anchor, anchor + timedelta(days=1), "today")
    if re.search(r"\bdun\b|\bdunku\b", q):
        return Period(anchor - timedelta(days=1), anchor, "yesterday")
    if re.search(r"\bbu hafta\w*", q):
        start = anchor - timedelta(days=anchor.weekday())
        return Period(start, start + timedelta(days=7), "this_week")
    if re.search(r"\bgecen hafta\w*", q):
        start = anchor - timedelta(days=anchor.weekday() + 7)
        return Period(start, start + timedelta(days=7), "last_week")
    if re.search(r"\bbu ay\w*", q):
        return _month_period(anchor.year, anchor.month, "this_month")
    if re.search(r"\bgecen ay\w*", q):
        prev = anchor.replace(day=1) - timedelta(days=1)
        return _month_period(prev.year, prev.month, "last_month")
    if re.search(r"\bbu (yil|sene)\w*", q):
        return Period(
            date(anchor.year, 1, 1), date(anchor.year + 1, 1, 1), "this_year", {"year": anchor.year}
        )
    if re.search(r"\bgecen (yil|sene)\w*", q):
        y = anchor.year - 1
        return Period(date(y, 1, 1), date(y + 1, 1, 1), "last_year", {"year": y})
    year_match = _YEAR.search(q)
    month_match = _MONTH.search(q)
    if month_match:
        month = MONTHS.index(month_match.group(1)) + 1
        if year_match:
            year = int(year_match.group(1))
        else:  # "Mart" means the most recent March up to the anchor date
            year = anchor.year if month <= anchor.month else anchor.year - 1
        return _month_period(year, month)
    if year_match:
        y = int(year_match.group(1))
        return Period(date(y, 1, 1), date(y + 1, 1, 1), "year", {"year": y})
    return None


def detect_customer(q: str, entities: list[EntityName]) -> tuple[int, str] | None:
    best: tuple[int, str, int] | None = None
    padded = f" {q} "
    for entity in entities:
        for key in entity.keys:
            if len(key) >= 4 and f" {key} " in padded and (best is None or len(key) > best[2]):
                best = (entity.id, entity.name, len(key))
    return (best[0], best[1]) if best else None


# A capitalised name followed by a Turkish case suffix: "Ahmet Yılmaz'ın", "Ayşe'ye".
_NAMED = re.compile(
    r"([A-ZÇĞİÖŞÜ][\wçğıöşü.]*(?:\s+[A-ZÇĞİÖŞÜ][\wçğıöşü.]*)*)['’]"
    r"(?:n?[ıiuü]n|y?[ae]|d[ae]n?|t[ae]n?|n?[ıiuü])(?!\w)"
)


def mentioned_name(question: str) -> str | None:
    """A person the question names explicitly, e.g. "Ahmet Yılmaz'ın" → "Ahmet Yılmaz".
    Month names ("Mart'ta") are not people."""
    for m in _NAMED.finditer(question):
        name = m.group(1).strip()
        if fold(name) not in MONTHS:
            return name
    return None


def plan_question(question: str, *, anchor: date, entities: list[EntityName]) -> Plan | None:
    q = normalize_question(question)
    period = detect_period(q, anchor)
    customer = detect_customer(q, entities)
    named = mentioned_name(question)
    if named and customer is None:
        # Never answer for everybody when the user asked about one person we do not know.
        raise PlanError("customer_not_found", name=named)

    if _COUNT_CUSTOMERS.search(q):
        plan = Plan(metric="customers", aggregate="count")
    elif _COUNT_RECORDS.search(q):
        plan = Plan(metric="count", aggregate="count")
    elif _BALANCE.search(q):
        plan = Plan(metric="balance")
    elif _PAYMENTS.search(q):
        plan = Plan(metric="payments")
    elif _SALES.search(q):
        plan = Plan(metric="sales")
    else:
        return None

    if _AVERAGE.search(q) and plan.aggregate == "sum":
        plan.aggregate = "avg"
    if _BY_MONTH.search(q):
        plan.group = "month"
    elif _BY_DAY.search(q):
        plan.group = "day"
    elif _BY_CUSTOMER.search(q) and customer is None and plan.metric not in ("customers",):
        plan.group = "customer"
    if _DESC.search(q):
        plan.order = "desc"
    elif _ASC.search(q):
        plan.order = "asc"
    # "en çok borçlanan" without "kim": a ranking question is about customers.
    if (
        plan.order
        and plan.group is None
        and customer is None
        and plan.metric not in ("count", "customers")
    ):
        plan.group = "customer"
    if plan.group == "customer" or (plan.order and plan.group):
        m = _TOP_N.search(q)
        plan.limit = int(next(g for g in m.groups() if g)) if m else DEFAULT_TOP
        plan.order = plan.order or "desc"
    plan.period = period
    plan.customer = customer
    return plan


METRIC_LABELS = {
    "sales": "Borç",
    "payments": "Ödeme",
    "balance": "Bakiye",
    "count": "Kayıt sayısı",
    "customers": "Müşteri sayısı",
}


def _check_answerable(plan: Plan, schema: DatasetSchema) -> None:
    if plan.metric in ("sales", "payments", "balance") and not schema.has_money:
        raise PlanError("no_money")
    if plan.metric == "payments" and not schema.has_payments:
        raise PlanError("no_payments")
    if (plan.period or plan.group in ("month", "day")) and schema.date is None:
        raise PlanError("no_dates")
    needs_customer = plan.group == "customer" or plan.customer or plan.metric == "customers"
    if needs_customer and not schema.customer_expr:
        raise PlanError("no_customers")


def _measure(plan: Plan, schema: DatasetSchema) -> tuple[str, str | None]:
    """Return ``(select expression, money expression or None)``."""
    expr = {
        "sales": schema.sales_expr,
        "payments": schema.payments_expr,
        "balance": schema.net_expr,
    }.get(plan.metric)
    label = METRIC_LABELS[plan.metric]
    if plan.metric == "count":
        return f'count(*) AS "{label}"', None
    if plan.metric == "customers":
        return f'count(DISTINCT {schema.customer_expr}) AS "{label}"', None
    if plan.aggregate == "avg":
        return f'round(avg({expr}), 2) AS "Ortalama {label.lower()}"', expr
    return f'sum({expr}) AS "{label}"', expr


def _dimension(plan: Plan, schema: DatasetSchema) -> str | None:
    if plan.group == "customer":
        return f'{schema.customer_expr} AS "Müşteri"'
    if schema.date is None:
        return None
    d = schema.q(schema.date)
    if plan.group == "month":
        return f"strftime(date_trunc('month', {d}), '%Y-%m') AS \"Ay\""
    if plan.group == "day":
        return f'{d} AS "Gün"'
    return None


def plan_to_sql(plan: Plan, schema: DatasetSchema) -> str:
    """Render a plan with the dataset's money model. Raises PlanError when the dataset
    cannot answer it (no money, no dates, no customers)."""
    _check_answerable(plan, schema)
    measure, expr = _measure(plan, schema)
    dimension = _dimension(plan, schema)

    where: list[str] = []
    if plan.period and schema.date is not None:
        d = schema.q(schema.date)
        where.append(f"{d} >= DATE '{plan.period.start.isoformat()}'")
        where.append(f"{d} < DATE '{plan.period.end.isoformat()}'")
    if plan.customer:
        where.append(f'"party_id" = {int(plan.customer[0])}')

    select = [dimension, measure] if dimension else [measure]
    lines = [f"SELECT {', '.join(select)}", f"FROM {schema.view}"]
    if where:
        lines.append("WHERE " + "\n  AND ".join(where))
    if dimension:
        lines.append("GROUP BY 1")
        if plan.metric == "balance" and plan.group == "customer" and plan.order == "desc":
            lines.append(f"HAVING sum({expr}) > 0")
        if plan.order:
            lines.append(f"ORDER BY 2 {'DESC' if plan.order == 'desc' else 'ASC'}")
        elif plan.group in ("month", "day"):
            lines.append("ORDER BY 1")
    if plan.limit:
        lines.append(f"LIMIT {int(plan.limit)}")
    return "\n".join(lines)


def suggest_chart(plan: Plan) -> str:
    if plan.group == "customer":
        return "bar"
    if plan.group in ("month", "day"):
        return "column"
    return "kpi"


def explain(plan: Plan) -> dict[str, Any]:
    out: dict[str, Any] = {"metric": plan.metric, "aggregate": plan.aggregate, "group": plan.group}
    if plan.order:
        out["order"] = plan.order
    if plan.limit:
        out["limit"] = plan.limit
    if plan.period:
        out["period"] = {
            "code": plan.period.code,
            "start": plan.period.start.isoformat(),
            "end": (plan.period.end - timedelta(days=1)).isoformat(),
            **plan.period.params,
        }
    if plan.customer:
        out["customer"] = {"id": plan.customer[0], "name": plan.customer[1]}
    return out
