"""Reliability, isolation and pagination regression tests."""

import pytest

from mem.apply import apply_patch
from mem.backup import create_backup
from mem.documents import load_documents
from mem.errors import MemoryError
from mem.health import get_health
from mem.inbox import list_inbox, read_inbox
from mem.models import MemoryPatch, SearchRequest
from mem.read import read_memory
from mem.search import search_memory

from .helpers import sample_patch


@pytest.mark.parametrize(
    "bad", [b"not a document", bytes([255]), b"x" * (1024 * 1024 + 1)]
)
def test_bad_document_does_not_block_valid_memory(store, bad):
    applied = apply_patch(store, sample_patch())
    (store.root / "L2/bad.md").write_bytes(bad)
    hits = search_memory(store, SearchRequest(query="smoke"))
    assert "L2/bad.md" in hits.invalid_sources
    assert (
        read_memory(store, "mem://document/" + applied.id_map["new:d"]).data["title"]
        == "Mem project"
    )
    assert get_health(store).ready is False
    with pytest.raises(MemoryError):
        create_backup(store, store.root.parent / "unsafe.zip")
    assert (
        apply_patch(store, MemoryPatch(idempotency_key="second")).state == "DONE"
    )


def test_tolerant_frontmatter_keeps_original_bytes(store):
    a = apply_patch(store, sample_patch())
    path = store.root / "L1/projects.md"
    raw = path.read_bytes().replace(b"---\n", b"---\ntags: [foo]\n", 1)
    raw = bytes([239, 187, 191]) + raw.replace(b"\n", b"\r\n")
    path.write_bytes(raw)
    loaded = load_documents(store)
    assert loaded[0].raw == raw
    assert search_memory(store, SearchRequest(query="SQLite")).invalid_sources == []
    assert (
        read_memory(store, "mem://document/" + a.id_map["new:d"]).source_etag
        == loaded[0].sha256
    )


def test_bad_duplicate_id_isolated(store):
    apply_patch(store, sample_patch())
    raw = (store.root / "L1/projects.md").read_bytes()
    (store.root / "L2/copy.md").write_bytes(raw)
    result = search_memory(store, SearchRequest(query="smoke"))
    assert result.invalid_sources == ["L2/copy.md"]
    assert result.items


def test_inbox_status_and_nested_pagination(store):
    inbox = store.root / "L0/Inbox"
    (inbox / "a").mkdir()
    (inbox / "a" / "first.md").write_text("first")
    (inbox / "a" / "second.md").write_text("second")
    (inbox / "b.bin").write_bytes(bytes([255, 254]))
    (inbox / "huge.txt").write_bytes(b"x" * (10 * 1024 * 1024 + 1))
    (inbox / "z.txt").write_text("last")
    seen = []
    cursor = None
    while True:
        page = list_inbox(store, cursor=cursor, limit=2)
        seen.extend(page.items)
        if page.next_cursor is None:
            break
        assert page.next_cursor == page.items[-1]["relative_path"]
        cursor = page.next_cursor
    assert len(seen) == 5
    assert len({i["relative_path"] for i in seen}) == 5
    statuses = {i["relative_path"]: i["status"] for i in seen}
    assert statuses["L0/Inbox/b.bin"] == "not_utf8"
    assert statuses["L0/Inbox/huge.txt"] == "too_large"
    assert statuses["L0/Inbox/z.txt"] == "ok"
    with pytest.raises(MemoryError):
        read_inbox(store, "L0/Inbox/b.bin", "0" * 64)


def test_symlink_inbox_item_is_diagnostic_not_global_failure(store, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("private")
    (store.root / "L0/Inbox/link.txt").symlink_to(outside)
    page = list_inbox(store)
    assert page.items[0]["status"] == "unreadable"
    assert page.items[0]["sha256"] is None
