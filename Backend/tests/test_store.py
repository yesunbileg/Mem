import subprocess
import sys

import pytest

from mem.errors import MemoryError
from mem.models import MemoryPatch, SearchRequest, SourceDraft
from mem.store import init_store, open_store


def test_store_reopen_and_init_preserve_data(tmp_path):
    s = init_store(tmp_path / "memory")
    assert s.db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert s.db.execute("PRAGMA synchronous").fetchone()[0] == 2
    s.db.execute("INSERT INTO topics VALUES ('t', 'Device', 1)")
    s.db.commit()
    s.close()
    s = init_store(tmp_path / "memory")
    assert s.db.execute("SELECT title FROM topics").fetchone()[0] == "Device"
    assert s.db.execute("PRAGMA user_version").fetchone()[0] == 2
    s.close()


def test_second_process_cannot_open_store(tmp_path):
    s = init_store(tmp_path / "memory")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from mem.store import open_store; import sys; open_store(sys.argv[1])",
            str(s.root),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "STORE_BUSY" in result.stderr
    s.close()
    open_store(tmp_path / "memory").close()


def test_missing_and_future_schema_rejected(tmp_path):
    with pytest.raises(MemoryError, match="NOT_FOUND"):
        open_store(tmp_path / "missing")
    s = init_store(tmp_path / "m")
    s.db.execute("PRAGMA user_version=99")
    s.close()
    with pytest.raises(MemoryError, match="SCHEMA_UNSUPPORTED"):
        open_store(tmp_path / "m")


def test_limits_and_unknown_fields():
    assert SearchRequest(query="test", limit=100).limit == 100
    for args in [
        {"query": ""},
        {"query": "x" * 501},
        {"query": "a", "limit": 101},
        {"query": "a", "limit": 0},
    ]:
        with pytest.raises(ValueError):
            SearchRequest(**args)
    SourceDraft(
        ref="new:s", kind="session", origin_ref="session:1", excerpt="a" * 65536
    )
    with pytest.raises(ValueError):
        SourceDraft(ref="new:s", kind="session", origin_ref="s", excerpt="a" * (10 * 1024 * 1024 + 1))
    with pytest.raises(ValueError):
        MemoryPatch(idempotency_key="k", mystery=True)
