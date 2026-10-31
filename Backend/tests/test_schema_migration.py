"""Non-destructive v1 to v2 migration safety regression tests."""

import sqlite3
from importlib.resources import files

import pytest

from mem.errors import MemoryError
from mem.schema_migration import migrate_v1_database
from mem.store import open_store


def _v1_database(path, *, pending=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript(
            files("mem").joinpath("migrations/001_initial.sql").read_text()
        )
        db.execute(
            "INSERT INTO sources(id,kind,origin_ref,excerpt,sha256,archive_ref) "
            "VALUES (?,?,?,?,?,NULL)",
            ("e68a3e15-1111-4111-8111-111111111111", "session",
             "session:legacy", "Original short excerpt", "sha"),
        )
        if pending:
            db.execute(
                "INSERT INTO operations(id,key,fingerprint,payload,state,result) "
                "VALUES (?,?,?,?,?,?)",
                ("a", "b", "c", "{}", "PREPARED", "{}"),
            )
        db.commit()


def test_v1_migration_is_explicit_verified_and_source_untouched(tmp_path):
    source = tmp_path / "v1.sqlite3"
    destination = tmp_path / "v2.sqlite3"
    _v1_database(source)
    original_bytes = source.read_bytes()
    result = migrate_v1_database(source, destination)
    assert result["source_unchanged"] is True
    assert source.read_bytes() == original_bytes
    with sqlite3.connect(source) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    with sqlite3.connect(destination) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert db.execute("SELECT full_text FROM sources").fetchone()[0] == (
            "Original short excerpt"
        )
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with pytest.raises(MemoryError, match="CONFLICT"):
        migrate_v1_database(source, destination)


def test_migration_rejects_pending_journal_without_publishing(tmp_path):
    source = tmp_path / "pending.sqlite3"
    destination = tmp_path / "must-not-exist.sqlite3"
    _v1_database(source, pending=True)
    with pytest.raises(MemoryError, match="RECOVERY_CONFLICT"):
        migrate_v1_database(source, destination)
    assert not destination.exists()


def test_migrated_v2_can_be_opened_without_changing_old_source(tmp_path):
    root = tmp_path / "memory"
    source = tmp_path / "old.sqlite3"
    _v1_database(source)
    destination = root / "L1/history.sqlite3"
    migrate_v1_database(source, destination)
    with open_store(root) as store:
        assert store.schema_version == 2
        assert store.db.execute("SELECT count(*) FROM sources").fetchone()[0] == 1
    with sqlite3.connect(source) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
