import hashlib
import json
import sqlite3
import zipfile

import pytest

from mem.apply import apply_patch
from mem.backup import create_backup, create_snapshot, restore_backup, restore_snapshot
from mem.errors import MemoryError
from mem.models import SearchRequest
from mem.search import search_memory
from mem.store import open_store

from .helpers import count_events, sample_patch
from .test_archive import inbox_patch


def test_backup_restore_preserves_canonical_sources(store, tmp_path):
    apply_patch(store, sample_patch())
    p, raw = inbox_patch(store)
    apply_patch(store, p)
    (store.root / "L0/Inbox/unprocessed.md").write_text("raw new")
    backup = tmp_path / "backup.zip"
    manifest = create_backup(store, backup)
    assert "L3/history.sqlite3" in manifest.files
    assert not any(".state" in n for n in manifest.files)
    dest = tmp_path / "restored"
    assert restore_backup(backup, dest).ready
    with open_store(dest) as s:
        assert count_events(s) == 1
        assert (dest / "L1/projects.md").read_bytes() == (
            store.root / "L1/projects.md"
        ).read_bytes()
        assert (dest / "L0/Inbox/unprocessed.md").read_text() == "raw new"
        assert search_memory(s, SearchRequest(query="smoke")).items
        assert (
            s.db.execute('SELECT excerpt FROM sources WHERE kind="session"').fetchone()[
                0
            ]
            == "MCP smoke test FAIL observed"
        )
    assert {p.name: p.read_bytes() for p in (dest / "L0/Archive").rglob("*.zip")} == {
        p.name: p.read_bytes() for p in (store.root / "L0/Archive").rglob("*.zip")
    }


def test_snapshot_is_consistent_and_restores_explicitly(store, tmp_path):
    apply_patch(store, sample_patch())
    snapshot = create_snapshot(store)
    with sqlite3.connect(snapshot) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 1
    target = tmp_path / "db.sqlite3"
    restore_snapshot(snapshot, target)
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 1
    with pytest.raises(MemoryError):
        restore_snapshot(snapshot, target)


@pytest.mark.parametrize("member", ["../escape", "/tmp/evil", "L1/../../out"])
def test_restore_rejects_zip_traversal(tmp_path, member):
    p = tmp_path / "bad.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(member, "bad")
        z.writestr(
            "manifest.json",
            json.dumps(
                {
                    "files": {member: hashlib.sha256(b"bad").hexdigest()},
                    "schema_version": 1,
                }
            ),
        )
    with pytest.raises(MemoryError):
        restore_backup(p, tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_restore_rejects_nonempty_and_corrupt_backup(store, tmp_path):
    apply_patch(store, sample_patch())
    p = tmp_path / "b.zip"
    create_backup(store, p)
    with pytest.raises(MemoryError):
        restore_backup(p, store.root)
    corrupt = tmp_path / "c.zip"
    with zipfile.ZipFile(p) as src, zipfile.ZipFile(corrupt, "w") as dst:
        for name in src.namelist():
            dst.writestr(
                name, b"corrupt" if name == "L1/projects.md" else src.read(name)
            )
    with pytest.raises(MemoryError):
        restore_backup(corrupt, tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_pending_conflict_blocks_backup(store, tmp_path):
    from mem.journal import prepare_operation

    prepare_operation(store, sample_patch())
    (store.root / "L1/projects.md").write_bytes(b"external")
    with pytest.raises(MemoryError):
        create_backup(store, tmp_path / "b.zip")
    with pytest.raises(MemoryError):
        create_snapshot(store)


def test_external_change_during_backup_rejected(store, tmp_path, monkeypatch):
    import mem.backup as b

    apply_patch(store, sample_patch())
    original = b._inventory
    calls = 0

    def changing(s):
        nonlocal calls
        calls += 1
        if calls == 2:
            path = s.root / "L1/projects.md"
            path.write_bytes(path.read_bytes() + b"\nchanged")
        return original(s)

    monkeypatch.setattr(b, "_inventory", changing)
    with pytest.raises(MemoryError, match="CONFLICT"):
        create_backup(store, tmp_path / "changed.zip")
    assert not (tmp_path / "changed.zip").exists()
