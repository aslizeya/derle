"""Turkish question understanding. Each case is a question a shopkeeper would type."""

from datetime import date

import pytest

from derle.analytics.schema import Column, DatasetSchema
from derle.nlq.rules import (
    EntityName,
    PlanError,
    detect_period,
    mentioned_name,
    normalize_question,
    plan_question,
    plan_to_sql,
)

ANCHOR = date(2026, 6, 30)
ENTITIES = [
    EntityName(1, "Mehmet Yılmaz", ("mehmet yilmaz", "m yilmaz")),
    EntityName(2, "Ayşe Kaya", ("ayse kaya", "ayse")),
]
LEDGER = DatasetSchema(
    dataset_id=4,
    workspace_id=1,
    name="Defter",
    view="ds_4",
    columns=(
        Column("date", "date", "Tarih", "date", "date"),
        Column("party", "party", "Müşteri", "party", "text"),
        Column("debit", "debit", "Borç", "debit", "number"),
        Column("credit", "credit", "Ödeme", "credit", "number"),
    ),
)


def plan(question: str):  # type: ignore[no-untyped-def]
    return plan_question(question, anchor=ANCHOR, entities=ENTITIES)


@pytest.mark.parametrize(
    ("question", "metric", "group", "order"),
    [
        ("Geçen ay en çok kim borçlandı?", "sales", "customer", "desc"),
        ("En çok borcu olan müşteriler", "balance", "customer", "desc"),
        ("Hangi ay en çok satış yaptık?", "sales", "month", "desc"),
        ("Aylık ödemeler", "payments", "month", None),
        ("Kaç müşterim var?", "customers", None, None),
        ("Kaç işlem var", "count", None, None),
        ("En az alışveriş yapan kim", "sales", "customer", "asc"),
        ("Toplam tahsilat ne kadar", "payments", None, None),
    ],
)
def test_intent(question: str, metric: str, group: str | None, order: str | None) -> None:
    p = plan(question)
    assert p is not None
    assert (p.metric, p.group, p.order) == (metric, group, order)


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [
        ("gecen ay", date(2026, 5, 1), date(2026, 6, 1)),
        ("bu ay", date(2026, 6, 1), date(2026, 7, 1)),
        ("bu yil", date(2026, 1, 1), date(2027, 1, 1)),
        ("gecen sene", date(2025, 1, 1), date(2026, 1, 1)),
        ("martta", date(2026, 3, 1), date(2026, 4, 1)),
        ("agustos", date(2025, 8, 1), date(2025, 9, 1)),  # the most recent August
        ("mart 2025", date(2025, 3, 1), date(2025, 4, 1)),
        ("2025 yilinda", date(2025, 1, 1), date(2026, 1, 1)),
        ("son 7 gun", date(2026, 6, 24), date(2026, 7, 1)),
        ("dun", date(2026, 6, 29), date(2026, 6, 30)),
    ],
)
def test_periods(text: str, start: date, end: date) -> None:
    period = detect_period(text, ANCHOR)
    assert period is not None
    assert (period.start, period.end) == (start, end)


def test_question_normalization_drops_suffixes_and_diacritics() -> None:
    assert normalize_question("Mehmet Yılmaz'ın Mart'taki borcu?") == "mehmet yilmaz mart borcu"


def test_customer_filter_from_possessive_name() -> None:
    p = plan("Mehmet Yılmaz'ın borcu ne kadar?")
    assert p is not None
    assert p.customer == (1, "Mehmet Yılmaz")
    assert p.group is None
    assert '"party_id" = 1' in plan_to_sql(p, LEDGER)


def test_unknown_person_is_an_error_not_a_total() -> None:
    with pytest.raises(PlanError) as info:
        plan("Ahmet Demir'in borcu ne kadar?")
    assert info.value.code == "customer_not_found"
    assert info.value.params == {"name": "Ahmet Demir"}


def test_month_names_are_not_people() -> None:
    assert mentioned_name("Mart'ta ne kadar ödeme alındı?") is None


def test_top_n() -> None:
    p = plan("En çok borcu olan 5 müşteri")
    assert p is not None and p.limit == 5
    assert plan_to_sql(p, LEDGER).endswith("LIMIT 5")


def test_unrelated_question_is_not_understood() -> None:
    assert plan("Hava nasıl?") is None


def test_balance_sql_uses_money_model() -> None:
    p = plan("En çok borcu olan müşteriler")
    assert p is not None
    sql = plan_to_sql(p, LEDGER)
    assert 'coalesce("debit", 0)' in sql and 'coalesce("credit", 0)' in sql
    assert "HAVING" in sql


def test_dataset_without_money_cannot_answer_money_questions() -> None:
    names_only = DatasetSchema(
        1, 1, "x", "ds_1", (Column("party", "party", "Ad", "party", "text"),)
    )
    p = plan("Toplam borç ne kadar")
    assert p is not None
    with pytest.raises(PlanError, match="no_money"):
        plan_to_sql(p, names_only)
