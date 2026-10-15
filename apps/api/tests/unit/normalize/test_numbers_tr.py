from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from derle.normalize.tr.numbers import (
    NumberStyle,
    format_decimal,
    infer_number_style,
    parse_number,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.234,56", "1234.56"),
        ("1,234.56", "1234.56"),
        ("1.234.567", "1234567"),
        ("1,234,567", "1234567"),
        ("1.234.567,89", "1234567.89"),
        ("12,5", "12.5"),
        ("12.5", "12.5"),
        ("0,750", "0.750"),
        ("0.750", "0.750"),
        ("1250", "1250"),
        (",5", "0.5"),
        ("1 250,00", "1250.00"),
        ("1'250", "1250"),
    ],
)
def test_unambiguous_formats(text: str, expected: str) -> None:
    parsed = parse_number(text)
    assert parsed is not None
    assert parsed.value == Decimal(expected)
    assert not parsed.ambiguous


@pytest.mark.parametrize(
    ("text", "expected", "currency"),
    [
        ("1.250,00 TL", "1250.00", "TRY"),
        ("₺1.250", "1250", "TRY"),
        ("1250 lira", "1250", "TRY"),
        ("1.250 TL.", "1250", "TRY"),
        ("TRY 99,90", "99.90", "TRY"),
        ("$40", "40", "USD"),
        ("40 Dolar", "40", "USD"),
        ("€ 12,50", "12.50", "EUR"),
        ("1.250 LİRA", "1250", "TRY"),
    ],
)
def test_currency_is_stripped_and_reported(text: str, expected: str, currency: str) -> None:
    parsed = parse_number(text)
    assert parsed is not None
    assert parsed.value == Decimal(expected)
    assert parsed.currency == currency


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("-150", "-150"),
        ("(1.250,00)", "-1250.00"),
        ("150-", "-150"),
        ("−75,5", "-75.5"),
        ("+20", "20"),
    ],
)
def test_negative_forms(text: str, expected: str) -> None:
    parsed = parse_number(text)
    assert parsed is not None
    assert parsed.value == Decimal(expected)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("2 bin", "2000"), ("1,5 milyon", "1500000"), ("bin", "1000"), ("3 Bin TL", "3000")],
)
def test_turkish_number_words(text: str, expected: str) -> None:
    parsed = parse_number(text)
    assert parsed is not None
    assert parsed.value == Decimal(expected)


def test_single_separator_with_three_digits_is_ambiguous_and_defaults_to_turkish() -> None:
    dotted = parse_number("1.250")
    comma = parse_number("1,250")
    assert dotted is not None and comma is not None
    assert dotted.ambiguous and comma.ambiguous
    assert dotted.value == Decimal(1250)  # TR: dot = thousands
    assert comma.value == Decimal("1.250")  # TR: comma = decimal


def test_column_hint_resolves_ambiguity() -> None:
    parsed = parse_number("1,250", NumberStyle.EN)
    assert parsed is not None
    assert parsed.value == Decimal(1250)
    assert not parsed.ambiguous


@pytest.mark.parametrize(
    "text", ["", "abc", "12a", "1.2.3,4,5", "1,23,45", "TL", "--", "12/03/2026", "0532 123 45 67x"]
)
def test_non_numbers_return_none(text: str) -> None:
    assert parse_number(text) is None


def test_infer_style_from_column() -> None:
    assert infer_number_style(["1.250", "980,50", "2.100,00"]) == NumberStyle.TR
    assert infer_number_style(["1,250", "980.50", "2,100.00"]) == NumberStyle.EN
    assert infer_number_style(["1.250", "3.400"]) is None


def test_format_decimal() -> None:
    assert format_decimal(Decimal("1250.00")) == "1250"
    assert format_decimal(Decimal("12.50")) == "12.5"
    assert format_decimal(Decimal("1E+3")) == "1000"


def _format_tr(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    integer, frac = f"{abs(value):.2f}".split(".")
    groups = []
    while integer:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    return f"{sign}{'.'.join(groups)},{frac}"


@given(st.decimals(min_value=-10_000_000, max_value=10_000_000, places=2, allow_nan=False))
def test_roundtrip_turkish_formatting(value: Decimal) -> None:
    parsed = parse_number(_format_tr(value))
    assert parsed is not None
    assert parsed.value == value


@given(st.decimals(min_value=0, max_value=10_000_000, places=2, allow_nan=False))
def test_roundtrip_english_formatting(value: Decimal) -> None:
    parsed = parse_number(f"{value:,.2f}")
    assert parsed is not None
    assert parsed.value == value
