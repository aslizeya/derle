from datetime import date

import pytest

from derle.normalize.tr.dates import (
    DateContext,
    DateOrder,
    infer_date_order,
    parse_date,
    year_from_filename,
)

CTX = DateContext(default_year=2026)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("15 Mart 2026", date(2026, 3, 15)),
        ("15 mart 2026", date(2026, 3, 15)),
        ("15 MART 2026", date(2026, 3, 15)),
        ("1 Şubat 2026", date(2026, 2, 1)),
        ("1 subat 2026", date(2026, 2, 1)),
        ("3 Ağustos 2026", date(2026, 8, 3)),
        ("3 agustos 26", date(2026, 8, 3)),
        ("12 Eylül 2025", date(2025, 9, 12)),
        ("30 Kasım 2025", date(2025, 11, 30)),
        ("31 Aralık 2025", date(2025, 12, 31)),
        ("5 May 2026", date(2026, 5, 5)),
        ("15-Mar-2026", date(2026, 3, 15)),
        ("15.Mar.2026", date(2026, 3, 15)),
        ("Pazartesi 16 Mart 2026", date(2026, 3, 16)),
        ("16 Mart 2026 Pazartesi", date(2026, 3, 16)),
        ("15 mart'ta", date(2026, 3, 15)),
        ("March 15, 2026", date(2026, 3, 15)),
    ],
)
def test_textual_months(text: str, expected: date) -> None:
    parsed = parse_date(text, CTX)
    assert parsed is not None
    assert parsed.value == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("15.03.2026", date(2026, 3, 15)),
        ("15.03.26", date(2026, 3, 15)),
        ("15/03/2026", date(2026, 3, 15)),
        ("15-03-2026", date(2026, 3, 15)),
        ("5.3.2026", date(2026, 3, 5)),
        ("2026-03-15", date(2026, 3, 15)),
        ("2026.03.15", date(2026, 3, 15)),
        ("15032026", date(2026, 3, 15)),
        ("15.03.2026 14:30", date(2026, 3, 15)),
        ("2026-03-15 00:00:00", date(2026, 3, 15)),
    ],
)
def test_numeric_formats(text: str, expected: date) -> None:
    parsed = parse_date(text, CTX)
    assert parsed is not None
    assert parsed.value == expected
    assert not parsed.year_inferred


@pytest.mark.parametrize(
    ("text", "expected"),
    [("15/3", date(2026, 3, 15)), ("15.03", date(2026, 3, 15)), ("15 Mart", date(2026, 3, 15))],
)
def test_missing_year_uses_context(text: str, expected: date) -> None:
    parsed = parse_date(text, CTX)
    assert parsed is not None
    assert parsed.value == expected
    assert parsed.year_inferred


def test_missing_year_without_context_fails() -> None:
    assert parse_date("15/3", DateContext(default_year=None)) is None


def test_ambiguous_day_month_defaults_to_day_first() -> None:
    parsed = parse_date("03/04/2026", CTX)
    assert parsed is not None
    assert parsed.value == date(2026, 4, 3)
    assert parsed.ambiguous


def test_same_day_and_month_is_not_ambiguous() -> None:
    parsed = parse_date("04/04/2026", CTX)
    assert parsed is not None and not parsed.ambiguous


def test_month_first_is_proven_by_day_over_twelve() -> None:
    parsed = parse_date("03/25/2026", CTX)
    assert parsed is not None
    assert parsed.value == date(2026, 3, 25)
    assert parsed.proves_order == DateOrder.MDY


def test_column_order_switches_ambiguous_values() -> None:
    parsed = parse_date("03/04/2026", DateContext(default_year=2026, order=DateOrder.MDY))
    assert parsed is not None
    assert parsed.value == date(2026, 3, 4)


def test_infer_date_order() -> None:
    assert infer_date_order(["03/04/2026", "03/25/2026", "12/30/2026"]) == DateOrder.MDY
    assert infer_date_order(["03/04/2026", "25/03/2026"]) == DateOrder.DMY
    assert infer_date_order(["03/04/2026"]) == DateOrder.DMY


@pytest.mark.parametrize(
    "text", ["", "yarın", "31.02.2026", "32.01.2026", "15.13.2026", "1250", "Ahmet", "15 Martı"]
)
def test_invalid_dates(text: str) -> None:
    assert parse_date(text, CTX) is None


def test_two_digit_year_pivot() -> None:
    assert parse_date("01.01.69", CTX).value.year == 2069  # type: ignore[union-attr]
    assert parse_date("01.01.70", CTX).value.year == 1970  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("name", "year"),
    [("veresiye_mart_2026.xlsx", 2026), ("2025-12 defter.csv", 2025), ("defter.xlsx", None)],
)
def test_year_from_filename(name: str, year: int | None) -> None:
    assert year_from_filename(name) == year
