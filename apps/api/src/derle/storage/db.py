from __future__ import annotations

import importlib.util
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

from derle.storage.schema import MIGRATIONS

# DuckDB's Python client tries ``import pandas`` on every query with parameters. When pandas
# is not installed (we don't need it), each attempt walks sys.path again, which made the
# benchmark ~10x slower. A ``None`` entry makes those imports fail instantly.
if importlib.util.find_spec("pandas") is None:
    sys.modules.setdefault("pandas", None)  # type: ignore[arg-type]


class Database:
    """A single DuckDB connection shared by the process.

    DuckDB allows one writer process per file. Inside the process we hand out cursors and
    serialize writes with a lock; reads use their own cursor and can run concurrently.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(self.path)
        self._write_lock = threading.RLock()
        self.migrate()
        self._harden()

    def migrate(self) -> None:
        with self._write_lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version INTEGER PRIMARY KEY,"
                " applied_at TIMESTAMP DEFAULT current_timestamp)"
            )
            row = self._conn.execute("SELECT max(version) FROM schema_migrations").fetchone()
            current = row[0] if row and row[0] is not None else 0
            applied = False
            for version, sql in enumerate(MIGRATIONS, start=1):
                if version <= current:
                    continue
                self._conn.execute("BEGIN")
                try:
                    self._conn.execute(sql)
                    self._conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES (?)", [version]
                    )
                    self._conn.execute("COMMIT")
                    applied = True
                except Exception:
                    self._conn.execute("ROLLBACK")
                    raise
            if applied:
                # DuckDB 1.5 cannot replay ``ALTER TABLE`` from the write-ahead log for a table
                # whose column defaults to ``nextval(...)`` (migration 3 does exactly that):
                # after a crash the file would refuse to open. Checkpointing moves the schema
                # change into the database file, so the log only ever holds data changes.
                self._conn.execute("CHECKPOINT")

    def _harden(self) -> None:
        """Defence in depth for user-facing SQL (natural-language queries): the app never
        reads or writes files through SQL, so DuckDB's file and network access is switched
        off and the configuration locked. A query that slipped past the SQL guard still
        could not touch the file system."""
        self._conn.execute("SET enable_external_access = false")
        self._conn.execute("SET lock_configuration = true")

    @contextmanager
    def read(self) -> Iterator[duckdb.DuckDBPyConnection]:
        cursor = self._conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    @contextmanager
    def transaction(self) -> Iterator[duckdb.DuckDBPyConnection]:
        with self._write_lock:
            cursor = self._conn.cursor()
            cursor.execute("BEGIN")
            try:
                yield cursor
                cursor.execute("COMMIT")
            except Exception:
                cursor.execute("ROLLBACK")
                raise
            finally:
                cursor.close()

    def close(self) -> None:
        self._conn.close()
