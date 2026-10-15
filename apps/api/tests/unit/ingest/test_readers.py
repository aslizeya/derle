import pytest

from derle.ingest import UnsupportedFileError, read_grids
from derle.ingest.csv_reader import decode_text, sniff_delimiter
from tests.conftest import make_csv


def test_decode_cp1254_turkish_characters() -> None:
    text, encoding = decode_text("Şükrü Işık;Gülşen".encode("cp1254"))
    assert text == "Şükrü Işık;Gülşen"
    assert encoding == "cp1254"


def test_decode_utf8_with_bom() -> None:
    text, encoding = decode_text("﻿Tarih;Tutar".encode())
    assert text == "Tarih;Tutar"
    assert encoding == "utf-8-sig"


def test_decode_utf16_excel_unicode_text() -> None:
    text, encoding = decode_text("Tarih\tTutar".encode("utf-16"))
    assert text == "Tarih\tTutar"
    assert encoding == "utf-16"


@pytest.mark.parametrize("delimiter", [";", ",", "\t", "|"])
def test_sniff_delimiter(delimiter: str) -> None:
    sample = "\n".join(delimiter.join(r) for r in [["Tarih", "Ad", "Tutar"], ["1", "a", "2"]] * 3)
    assert sniff_delimiter(sample) == delimiter


def test_semicolon_csv_with_decimal_commas() -> None:
    # Commas inside values must not be mistaken for the delimiter.
    data = make_csv([["Tarih", "Tutar"], ["01.03.2026", "1.250,50"], ["02.03.2026", "80,00"]])
    grid = read_grids(data, "mart.csv")[0]
    assert grid.meta["delimiter"] == ";"
    assert grid.rows[1].cells == ["01.03.2026", "1.250,50"]


def test_empty_cells_become_none() -> None:
    grid = read_grids(make_csv([["a", "", "c"]]), "x.csv")[0]
    assert grid.rows[0].cells == ["a", None, "c"]


def test_excel_keeps_native_types(ledger_xlsx: bytes) -> None:
    grid = read_grids(ledger_xlsx, "mart.xlsx")[0]
    assert grid.sheet == "Mart"
    first_data = grid.rows[3]
    assert first_data.index == 4
    assert first_data.cells[0] == "2026-03-01"
    assert first_data.native is not None
    assert first_data.native[2] == 1250.5


@pytest.mark.parametrize(
    ("filename", "code"),
    [("defter.xls", "legacy_xls"), ("defter.pdf", "unsupported_extension")],
)
def test_unsupported_files(filename: str, code: str) -> None:
    with pytest.raises(UnsupportedFileError) as info:
        read_grids(b"data", filename)
    assert info.value.code == code


def test_corrupt_excel() -> None:
    with pytest.raises(UnsupportedFileError) as info:
        read_grids(b"not a zip", "x.xlsx")
    assert info.value.code == "corrupt_excel"
