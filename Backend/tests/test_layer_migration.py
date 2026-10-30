"""Level numbering and lossless, offline v0.1 migration regression tests."""

import sqlite3

import pytest

from mem.apply import apply_patch
from mem.errors import MemoryError
from mem.legacy_migration import migrate_legacy_store
from mem.models import SearchRequest
from mem.search import search_memory
from mem.store import init_store, open_store

from .helpers import sample_patch


def _legacy_root(tmp_path, *, pending=False, snapshot_only=False):
    """Build valid old L1 Markdown / L3 DB layout without executing old code."""
    root = tmp_path / "old"
    with init_store(root) as store:
        result = apply_patch(store, sample_patch())
        if pending:
            from mem.journal import prepare_operation

            prepare_operation(store, sample_patch(key="unfinished"))
    document = root / "L3/projects.md"
    old_document = root / "L1/projects.md"
    old_document.write_bytes(document.read_bytes().replace(b"layer: L3", b"layer: L1"))
    document.unlink()
    original_db = root / "L1/history.sqlite3"
    target_db = root / "L3/history.sqlite3"
    original_db.replace(target_db)
    if snapshot_only:
        target_db.replace(root / "L3/history.snapshot.sqlite3")
    (root / "L0/Inbox/raw.txt").write_bytes(b"Unprocessed source preserved byte for byte")
    return root, result


def test_levels_progress_from_history_to_distilled_knowledge(tmp_path):
    root = tmp_path / "modern"
    with init_store(root) as store:
        a = apply_patch(store, sample_patch())
        doc = root / "L3/projects.md"
        assert doc.exists()
        assert (root / "L1/history.sqlite3").exists()
        assert b"layer: L3" in doc.read_bytes()
        hits = search_memory(store, SearchRequest(query="smoke")).items
        by_ref = {h.ref: h.layer for h in hits}
        assert by_ref["mem://document/" + a.id_map["new:d"]] == "L3"
        assert by_ref["mem://event/" + a.id_map["new:e"]] == "L1"


@pytest.mark.parametrize("snapshot_only", [False, True])
def test_migrate_legacy_store_preserves_data_and_original(tmp_path, snapshot_only):
    old, a = _legacy_root(tmp_path, snapshot_only=snapshot_only)
    raw_before = (old / "L1/projects.md").read_bytes()
    source_db = old / "L3" / (
        "history.snapshot.sqlite3" if snapshot_only else "history.sqlite3"
    )
    assert source_db.exists()
    new = tmp_path / "migrated"
    result = migrate_legacy_store(old, new)
    assert result["source_unchanged"] is True
    assert result["status"] == "verified"
    assert (old / "L1/projects.md").read_bytes() == raw_before
    assert source_db.exists()
    assert (new / "L0/Inbox/raw.txt").read_bytes() == (old / "L0/Inbox/raw.txt").read_bytes()
    assert b"layer: L3" in (new / "L3/projects.md").read_bytes()
    assert (new / "L1/history.snapshot.sqlite3").exists()
    with open_store(new) as store:
        hits = search_memory(store, SearchRequest(query="smoke")).items
        assert {h.ref for h in hits} == {
            "mem://document/" + a.id_map["new:d"],
            "mem://event/" + a.id_map["new:e"],
        }
        assert store.db.execute("SELECT count(*) FROM events").fetchone()[0] == 1
    with sqlite3.connect(source_db) as db:
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 1


def test_old_store_is_never_silently_reinitialized(tmp_path):
    root, _ = _legacy_root(tmp_path)
    with pytest.raises(MemoryError, match="SCHEMA_UNSUPPORTED"):
        init_store(root)
    with pytest.raises(MemoryError, match="SCHEMA_UNSUPPORTED"):
        open_store(root)
    assert (root / "L3/history.sqlite3").exists()
    assert not (root / "L1/history.sqlite3").exists()


def test_migrate_requires_completed_journal_and_preserves_old_store(tmp_path):
    root, _ = _legacy_root(tmp_path, pending=True)
    dest = tmp_path / "new"
    with pytest.raises(MemoryError, match="RECOVERY_CONFLICT"):
        migrate_legacy_store(root, dest)
    assert not dest.exists()
    assert (root / "L1/projects.md").exists()
    assert (root / "L3/history.sqlite3").exists()


def test_invalid_legacy_document_prevents_partial_publish(tmp_path):
    root, _ = _legacy_root(tmp_path)
    (root / "L1/bad.md").write_text("invalid frontmatter")
    new = tmp_path / "new"
    with pytest.raises(MemoryError, match="INDEX_INVALID"):
        migrate_legacy_store(root, new)
    assert not new.exists()
    assert (root / "L1/bad.md").exists()


def test_migration_will_not_overwrite_existing_destination(tmp_path):
    root, _ = _legacy_root(tmp_path)
    dest = tmp_path / "new"
    dest.mkdir()
    (dest / "important.txt").write_text("keep")
    with pytest.raises(MemoryError, match="CONFLICT"):
        migrate_legacy_store(root, dest)
    assert (dest / "important.txt").read_text() == "keep"
