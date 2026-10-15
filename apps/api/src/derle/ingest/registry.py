from __future__ import annotations

from pathlib import PurePath

from derle.ingest.base import RawGrid, SourceReader, UnsupportedFileError
from derle.ingest.csv_reader import CsvReader
from derle.ingest.excel_reader import ExcelReader

READERS: list[SourceReader] = [CsvReader(), ExcelReader()]


def reader_for(filename: str) -> SourceReader:
    suffix = PurePath(filename).suffix.lower()
    for reader in READERS:
        if suffix in reader.extensions:
            return reader
    if suffix == ".xls":
        raise UnsupportedFileError("legacy_xls", "save the file as .xlsx and upload again")
    raise UnsupportedFileError("unsupported_extension", suffix or "(none)")


def read_grids(data: bytes, filename: str) -> list[RawGrid]:
    return reader_for(filename).read(data, filename)
