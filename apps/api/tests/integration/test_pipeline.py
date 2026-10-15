"""End-to-end: bytes in → DuckDB rows with provenance and transformation logs out."""

from datetime import date

import pytest

from derle.domain.models import ColumnRole
from derle.services import queries
from derle.services.ingest import IngestError, UploadResult, ingest_file
from derle.storage.db import Database
from tests.conftest import make_csv

TODAY = date(2026, 10, 14)


def _ingest(db: Database, workspace_id: int, data: bytes, filename: str) -> UploadResult:
    return ingest_file(db, workspace_id=workspace_id, data=data, filename=filename, today=TODAY)


def test_excel_ledger_is_cleaned(db: Database, workspace_id: int, ledger_xlsx: bytes) -> None:
    result = ingest_file(
        db, workspace_id=workspace_id, data=ledger_xlsx, filename="mart_2026.xlsx", today=TODAY
    )
    (table,) = result.tables
    roles = {c.header: c.role for c in table.columns}
    assert roles == {
        "Tarih": ColumnRole.DATE,
        "Müşteri": ColumnRole.PARTY,
        "Tutar": ColumnRole.AMOUNT,
        "Telefon": ColumnRole.PHONE,
        "Açıklama": ColumnRole.DESCRIPTION,
    }
    assert table.rows_total == 6
    assert table.duplicates == 1
    assert table.rows_imported == 5
    assert table.skipped == {"title": 1, "empty": 1, "total": 1}

    with db.read() as cur:
        rows, total = queries.list_records(cur, table.dataset_id, limit=50, offset=0)
    assert total == 5
    by_party = [(r["date"], r["party"], r["amount"], r["phone"]) for r in rows]
    assert by_party == [
        ("2026-03-01", "Ahmet", 1250.5, "0532 123 45 67"),
        ("2026-03-02", "Ayşe", 980.0, "0532 987 65 43"),
        ("2026-03-03", "Mehmet Yılmaz", 1250.0, "0533 111 22 33"),
        ("2026-03-05", "Ahmet", 75.0, "0532 123 45 67"),
        ("2026-03-06", "Mehmet Yılmaz", 2400.0, None),
    ]


def test_every_cell_traces_back_to_its_source(
    db: Database, workspace_id: int, ledger_xlsx: bytes
) -> None:
    result = ingest_file(
        db, workspace_id=workspace_id, data=ledger_xlsx, filename="mart_2026.xlsx", today=TODAY
    )
    dataset_id = result.tables[0].dataset_id
    with db.read() as cur:
        rows, _ = queries.list_records(cur, dataset_id, limit=50, offset=0)
        dataset = queries.get_dataset(cur, dataset_id)
        assert dataset is not None
        fields = {f["key"]: f["id"] for f in dataset["fields"]}
        ayse = next(r for r in rows if r["party"] == "Ayşe")
        prov = queries.cell_provenance(cur, ayse["record_id"], fields["amount"])

    assert prov is not None
    assert prov["value"] == "980"
    assert prov["original"] == "980,00 TL"
    assert prov["source"]["filename"] == "mart_2026.xlsx"
    assert prov["source"]["sheet"] == "Mart"
    assert prov["source"]["row"] == 5
    assert prov["source"]["columns"] == [{"index": 2, "header": "Tutar"}]
    assert prov["source"]["raw_row"][1] == "AYŞE HANIM"
    kinds = [t["kind"] for t in prov["transforms"]]
    assert kinds == ["currency_stripped", "number_parsed"]


def test_inferred_year_is_logged_with_lower_confidence(
    db: Database, workspace_id: int, ledger_xlsx: bytes
) -> None:
    result = ingest_file(
        db, workspace_id=workspace_id, data=ledger_xlsx, filename="mart_2026.xlsx", today=TODAY
    )
    with db.read() as cur:
        rows = cur.execute(
            "SELECT before_value, after_value, confidence, detail->>'year_inferred' "
            "FROM transformations WHERE table_id = ? AND kind = 'date_parsed' ORDER BY id",
            [result.tables[0].table_id],
        ).fetchall()
    assert ("3 Mart", "2026-03-03", 0.8, "2026") in rows


def test_split_names_and_debit_credit_from_cp1254_csv(
    db: Database, workspace_id: int, ledger_csv_cp1254: bytes
) -> None:
    result = _ingest(db, workspace_id, ledger_csv_cp1254, "nisan.csv")
    (table,) = result.tables
    with db.read() as cur:
        rows, _ = queries.list_records(cur, table.dataset_id, limit=50, offset=0)
    assert [(r["party"], r["debit"], r["credit"]) for r in rows] == [
        ("Ahmet Yılmaz", 1500.0, None),
        ("Şükrü Işık", 320.5, None),
        ("Ahmet Yılmaz", None, 1000.0),
        ("Gülşen Çağlar", 45.0, None),
    ]


def test_second_upload_appends_and_removes_cross_file_duplicates(
    db: Database, workspace_id: int, ledger_xlsx: bytes
) -> None:
    first = _ingest(db, workspace_id, ledger_xlsx, "mart_2026.xlsx")
    second = _ingest(db, workspace_id, ledger_xlsx, "mart_2026_kopya.xlsx")
    t1, t2 = first.tables[0], second.tables[0]
    assert t2.dataset_id == t1.dataset_id
    assert not t2.created_dataset
    assert t2.duplicates == 6
    assert t2.rows_imported == 0
    assert first.version_id < second.version_id
    with db.read() as cur:
        _, total = queries.list_records(cur, t1.dataset_id, limit=1, offset=0)
    assert total == 5


def test_ledger_with_new_money_columns_joins_the_same_dataset(
    db: Database, workspace_id: int, ledger_xlsx: bytes, ledger_csv_cp1254: bytes
) -> None:
    # March used one "Tutar" column, April switched to "Borç / Ödeme": still the same ledger.
    a = _ingest(db, workspace_id, ledger_xlsx, "mart_2026.xlsx")
    b = _ingest(db, workspace_id, ledger_csv_cp1254, "nisan.csv")
    assert a.tables[0].dataset_id == b.tables[0].dataset_id
    with db.read() as cur:
        dataset = queries.get_dataset(cur, a.tables[0].dataset_id)
    assert dataset is not None
    assert {"amount", "debit", "credit"} <= {f["key"] for f in dataset["fields"]}


def test_different_shape_creates_new_dataset(
    db: Database, workspace_id: int, ledger_xlsx: bytes
) -> None:
    price_list = make_csv([["Ürün", "Kategori", "Fiyat"], ["Ekmek", "Fırın", "10"]])
    a = _ingest(db, workspace_id, ledger_xlsx, "mart_2026.xlsx")
    b = _ingest(db, workspace_id, price_list, "fiyatlar.csv")
    assert a.tables[0].dataset_id != b.tables[0].dataset_id
    with db.read() as cur:
        assert len(queries.list_datasets(cur, workspace_id)) == 2


def test_raw_rows_are_kept_verbatim_including_skipped_ones(
    db: Database, workspace_id: int, ledger_xlsx: bytes
) -> None:
    result = _ingest(db, workspace_id, ledger_xlsx, "mart_2026.xlsx")
    with db.read() as cur:
        rows = cur.execute(
            "SELECT row_index, skip_reason FROM raw_rows WHERE table_id = ? ORDER BY row_index",
            [result.tables[0].table_id],
        ).fetchall()
    assert len(rows) == 11
    assert dict(rows)[11] == "total"


def test_pipeline_events_tell_the_story(
    db: Database, workspace_id: int, ledger_xlsx: bytes
) -> None:
    result = _ingest(db, workspace_id, ledger_xlsx, "mart_2026.xlsx")
    codes = [e.code for e in result.events]
    assert codes[0] == "file_received"
    assert codes.count("column_recognized") == 5
    assert "duplicates_removed" in codes
    assert codes[-1] == "done"


def test_unreadable_file_is_recorded_as_failed(db: Database, workspace_id: int) -> None:
    with pytest.raises(IngestError) as info:
        _ingest(db, workspace_id, b"garbage", "x.xlsx")
    assert info.value.code == "corrupt_excel"
    assert info.value.upload_id is not None
    with db.read() as cur:
        upload = queries.get_upload(cur, info.value.upload_id)
    assert upload is not None and upload["status"] == "failed"
