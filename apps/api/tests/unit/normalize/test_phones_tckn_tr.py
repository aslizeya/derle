import pytest

from derle.normalize.tr.phones import mask_phone, parse_phone
from derle.normalize.tr.tckn import clean_tckn, is_valid_tckn, mask_tckn


@pytest.mark.parametrize(
    "text",
    [
        "0532 123 45 67",
        "05321234567",
        "5321234567",
        "+90 532 123 45 67",
        "+90 (532) 123-4567",
        "0090 532 123 45 67",
        "905321234567",
        "0 532 123 4567",
        "tel: 0532.123.45.67",
    ],
)
def test_mobile_formats(text: str) -> None:
    parsed = parse_phone(text)
    assert parsed is not None
    assert parsed.e164 == "+905321234567"
    assert parsed.national == "0532 123 45 67"
    assert parsed.is_mobile


def test_landline() -> None:
    parsed = parse_phone("(0212) 555 66 77")
    assert parsed is not None
    assert parsed.e164 == "+902125556677"
    assert not parsed.is_mobile


@pytest.mark.parametrize("text", ["", "123", "0532 123", "1234567890", "ahmet", "0632 123 45 67"])
def test_invalid_phones(text: str) -> None:
    assert parse_phone(text) is None


def test_mask_phone() -> None:
    assert mask_phone("0532 123 45 67") == "0532 *** ** 67"


# 10000000146 is the well-known valid test TCKN.
@pytest.mark.parametrize("value", ["10000000146", "100 000 001 46"])
def test_valid_tckn(value: str) -> None:
    assert clean_tckn(value) == "10000000146"


@pytest.mark.parametrize("value", ["10000000147", "00000000146", "1000000014", "abcdefghijk"])
def test_invalid_tckn(value: str) -> None:
    assert not is_valid_tckn(value)


def test_mask_tckn() -> None:
    assert mask_tckn("10000000146") == "100******46"
