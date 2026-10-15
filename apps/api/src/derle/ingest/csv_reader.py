from __future__ import annotations

import csv
import io

from derle.ingest.base import RawGrid, RawRow, UnsupportedFileError

_DELIMITERS = ";,\t|"
# Windows-1254 is what Turkish Excel writes for "CSV (virgülle ayrılmış)".
_FALLBACK_ENCODINGS = ("cp1254", "iso-8859-9")


def decode_text(data: bytes) -> tuple[str, str]:
    """Return ``(text, encoding)``, trying BOMs, strict UTF-8, then Turkish legacy encodings."""
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16"), "utf-16"
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    for encoding in _FALLBACK_ENCODINGS:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8-lossy"


def sniff_delimiter(sample: str) -> str:
    lines = [line for line in sample.splitlines()[:30] if line.strip()]
    if not lines:
        return ","
    try:
        return csv.Sniffer().sniff("\n".join(lines), delimiters=_DELIMITERS).delimiter
    except csv.Error:
        pass
    # Fallback: the delimiter whose per-line count is most consistent and non-zero.
    best, best_score = ",", -1.0
    for delim in _DELIMITERS:
        counts = [line.count(delim) for line in lines]
        if max(counts) == 0:
            continue
        mode = max(set(counts), key=counts.count)
        score = counts.count(mode) / len(counts) + (0.01 * mode if mode else 0)
        if mode and score > best_score:
            best, best_score = delim, score
    return best


class CsvReader:
    extensions: tuple[str, ...] = (".csv", ".tsv", ".txt")

    def read(self, data: bytes, filename: str) -> list[RawGrid]:
        if not data.strip():
            raise UnsupportedFileError("empty_file")
        text, encoding = decode_text(data)
        delimiter = "\t" if filename.lower().endswith(".tsv") else sniff_delimiter(text[:20_000])
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
        rows = [
            RawRow(index=i, cells=[cell if cell != "" else None for cell in record])
            for i, record in enumerate(reader, start=1)
        ]
        return [RawGrid(sheet=None, rows=rows, meta={"encoding": encoding, "delimiter": delimiter})]
