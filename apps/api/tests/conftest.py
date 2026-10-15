from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import date, datetime
from typing import Any

import pytest
from openpyxl import Workbook

from derle.storage import repo
from derle.storage.db import Database


def make_xlsx(sheets: dict[str, list[list[Any]]]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets.items():
        sheet = workbook.create_sheet(title)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def make_csv(rows: list[list[str]], *, delimiter: str = ";", encoding: str = "utf-8") -> bytes:
    return "\r\n".join(delimiter.join(r) for r in rows).encode(encoding)


@pytest.fixture
def db() -> Iterator[Database]:
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def workspace_id(db: Database) -> int:
    with db.transaction() as cur:
        return repo.ensure_default_workspace(cur)


@pytest.fixture
def ledger_xlsx() -> bytes:
    """A realistic hand-made veresiye sheet: title rows, mixed formats, a total row."""
    return make_xlsx(
        {
            "Mart": [
                ["KARDEŞLER BAKKALİYE - MART 2026 VERESİYE DEFTERİ"],
                [],
                ["Tarih", "Müşteri", "Tutar", "Telefon", "Açıklama"],
                [datetime(2026, 3, 1), "Ahmet bey", 1250.5, "0532 123 45 67", "ekmek, süt"],
                ["02.03.2026", "AYŞE HANIM", "980,00 TL", "05329876543", "deterjan"],
                ["3 Mart", "Mehmet Yılmaz", "1.250", "+90 (533) 111-2233", None],
                ["5/3", "ahmet bey", "75", "0532 123 45 67", "gazete"],
                ["5/3", "ahmet bey", "75", "0532 123 45 67", "gazete"],
                [date(2026, 3, 6), "Yılmaz, Mehmet", "₺2.400,00", None, "  kola   kasası "],
                [],
                ["TOPLAM", None, 6030.5, None, None],
            ]
        }
    )


@pytest.fixture
def ledger_csv_cp1254() -> bytes:
    """Same business, different month: Windows-1254 CSV, split name columns, debit/credit."""
    return make_csv(
        [
            ["Tarih", "Adı", "Soyadı", "Borç", "Ödeme"],
            ["01.04.2026", "Ahmet", "Yılmaz", "1.500,00", ""],
            ["03.04.2026", "Şükrü", "Işık", "320,50", ""],
            ["10.04.2026", "Ahmet", "Yılmaz", "", "1.000,00"],
            ["12.04.2026", "Gülşen", "Çağlar", "45", ""],
        ],
        encoding="cp1254",
    )
