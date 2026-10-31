"""Level numbering and lossless, offline v0.1 migration regression tests."""

import sqlite3
from importlib.resources import files

import pytest

from mem.apply import apply_patch
from mem.errors import MemoryError
from mem.legacy_migration import migrate_legacy_store
from mem.models import MemoryPatch, SearchRequest
from mem.search import search_memory
from mem.store import init_store, open_store

from .helpers import sample_patch
from .test_archive import inbox_patch


def _make_v1_database(modern_db, old_db):
    """Build a genuine schema-v1 fixture without silently converting user data."""
    tables = {
        "metadata": "key,value",
        "topics": "id,title,revision",
        "operations": "id,key,fingerprint,payload,state,result",
        "sources": "id,kind,origin_ref,excerpt,sha256,archive_ref",
        "events": "id,kind,summary,details,occurred_at,recorded_at,evidence_kind,corrects_event_id,operation_id",
        "event_topics": "event_id,topic_id",
        "event_sources": "event_id,source_id",
        "document_revisions": "id,document_id,before_bytes,operation_id,source_refs",
        "operation_documents": "operation_id,ordinal,path,before_bytes,after_bytes",
        "operation_sources": "operation_id,source_id,relative_path,sha256,raw,archive_filename,outcome,reason,archive_ref",
        "processed_sources": "sha256,archive_ref",
    }
    with sqlite3.connect(old_db) as old:
        old.executescript(files("mem").joinpath("migrations/001_initial.sql").read_text())
        old.execute("ATTACH DATABASE ? AS modern", (str(modern_db),))
        for table, columns in tables.items():
            action = "INSERT OR REPLACE" if table == "metadata" else "INSERT"
            old.execute(
                f"{action} INTO main.{table} ({columns}) SELECT {columns} FROM modern.{table}"
            )
        old.commit()
    old_db.replace(modern_db)


def _legacy_root(tmp_path, *, pending=False, snapshot_only=False):
    """Build valid old L1 Markdown / L3 DB layout without executing old code."""
    root = tmp_path / "old"
    with init_store(root) as store:
        result = apply_patch(store, sample_patch())
        archive_patch, _ = inbox_patch(store)
        apply_patch(store, archive_patch)
        if pending:
            from mem.journal import prepare_operation

            prepare_operation(store, MemoryPatch(idempotency_key="unfinished"))
    document = root / "L3/projects.md"
    old_document = root / "L1/projects.md"
    old_document.write_bytes(document.read_bytes().replace(b"layer: L3", b"layer: L1"))
    document.unlink()
    original_db = root / "L1/history.sqlite3"
    _make_v1_database(original_db, tmp_path / "v1-copy.sqlite3")
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
    old_archives = {
        p.relative_to(old).as_posix(): p.read_bytes()
        for p in (old / "L0/Archive").rglob("*.zip")
    }
    assert old_archives
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
    assert {
        p.relative_to(new).as_posix(): p.read_bytes()
        for p in (new / "L0/Archive").rglob("*.zip")
    } == old_archives
    with open_store(new) as store:
        hits = search_memory(store, SearchRequest(query="smoke")).items
        assert {h.ref for h in hits} == {
            "mem://document/" + a.id_map["new:d"],
            "mem://event/" + a.id_map["new:e"],
            "mem://source/" + a.id_map["new:s"],
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
