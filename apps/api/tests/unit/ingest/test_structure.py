from derle.ingest import RawGrid, RawRow
from derle.ingest.registry import read_grids
from derle.ingest.structure import detect_table


def _grid(rows: list[list[str | None]]) -> RawGrid:
    return RawGrid(sheet=None, rows=[RawRow(index=i, cells=r) for i, r in enumerate(rows, 1)])


def test_title_rows_total_row_and_blank_rows_are_skipped(ledger_xlsx: bytes) -> None:
    table = detect_table(read_grids(ledger_xlsx, "mart.xlsx")[0])
    assert table.header_row == 3
    assert table.headers == ["Tarih", "Müşteri", "Tutar", "Telefon", "Açıklama"]
    assert [r.index for r in table.rows] == [4, 5, 6, 7, 8, 9]
    reasons = {s.index: s.reason for s in table.skipped}
    assert reasons == {1: "title", 10: "empty", 11: "total"}


def test_repeated_header_rows_are_skipped() -> None:
    table = detect_table(
        _grid(
            [
                ["Tarih", "Müşteri", "Tutar"],
                ["01.03.2026", "Ali", "10"],
                ["Tarih", "Müşteri", "Tutar"],
                ["01.04.2026", "Veli", "20"],
            ]
        )
    )
    assert [r.index for r in table.rows] == [2, 4]
    assert table.skipped[0].reason == "repeated_header"


def test_headerless_file_gets_positional_headers() -> None:
    table = detect_table(
        _grid([["01.03.2026", "Ali Kaya", "10"], ["02.03.2026", "Veli Can", "20,5"]])
    )
    assert table.header_row is None
    assert table.headers == ["#1", "#2", "#3"]
    assert len(table.rows) == 2


def test_unknown_but_textual_header_is_detected() -> None:
    table = detect_table(_grid([["Gün", "Kişi", "Ne aldı"], ["01.03.2026", "Ali", "ekmek"]]))
    assert table.header_row == 1


def test_fully_empty_columns_are_dropped() -> None:
    table = detect_table(_grid([["Tarih", None, "Tutar"], ["01.03.2026", None, "10"]]))
    assert table.headers == ["Tarih", "Tutar"]
    assert table.col_indexes == [0, 2]


def test_ragged_rows_are_padded() -> None:
    table = detect_table(_grid([["Tarih", "Müşteri", "Tutar"], ["01.03.2026", "Ali"]]))
    assert table.rows[0].cells == ["01.03.2026", "Ali", None]
