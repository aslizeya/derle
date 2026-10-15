"""A process killed without closing the database must leave a file that opens again."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

from derle.storage import repo
from derle.storage.db import Database

_WRITE_AND_DIE = textwrap.dedent(
    """
    import os, sys
    from derle.storage import repo
    from derle.storage.db import Database

    db = Database(sys.argv[1])
    with db.transaction() as cur:
        workspace_id = repo.ensure_default_workspace(cur)
        repo.create_version(cur, workspace_id, "upload", "before the crash")
    os._exit(1)  # no close(), no checkpoint: the write-ahead log is all that is left
    """
)


def test_database_reopens_after_hard_kill(tmp_path: Path) -> None:
    path = tmp_path / "derle.duckdb"
    src = Path(repo.__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-c", _WRITE_AND_DIE, str(path)],
        env={**os.environ, "PYTHONPATH": str(src)},
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1, result.stderr
    assert path.with_suffix(".duckdb.wal").exists()

    db = Database(path)  # used to fail: "Failure while replaying WAL file"
    try:
        with db.read() as cur:
            workspaces = cur.execute("SELECT id FROM workspaces").fetchall()
            messages = [r[0] for r in cur.execute("SELECT message FROM versions").fetchall()]
        assert workspaces
        assert "before the crash" in messages
    finally:
        db.close()
