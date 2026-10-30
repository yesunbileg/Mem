import hashlib
import sqlite3

import pytest

from mem.apply import apply_patch
from mem.errors import MemoryError
from mem.models import MemoryPatch
from mem.read import read_memory

from .helpers import sample_patch


def test_duplicate_raw_content_in_one_patch_rejected(store):
    raw = b"question"
    sha = hashlib.sha256(raw).hexdigest()
    for name in ["one.md", "two.md"]:
        (store.root / "L0/Inbox" / name).write_bytes(raw)
    p = MemoryPatch(
        idempotency_key="two",
        close_inbox=[
            dict(
                relative_path="L0/Inbox/" + name,
                expected_sha256=sha,
                archive_filename=title,
                outcome="no_memory",
                reason="no facts",
            )
            for name, title in [("one.md", "Topic-one.md"), ("two.md", "Topic-two.md")]
        ],
    )
    with pytest.raises(MemoryError, match="SOURCE_ALREADY_PROCESSED"):
        apply_patch(store, p)
    assert not list((store.root / "L0/Archive").rglob("*.zip"))


def test_case_insensitive_archive_destination_collision_rejected(store):
    items = []
    for i, name in enumerate(["Topic.md", "topic.md"]):
        raw = str(i).encode()
        p = store.root / f"L0/Inbox/{i}.md"
        p.write_bytes(raw)
        items.append(
            dict(
                relative_path=f"L0/Inbox/{i}.md",
                expected_sha256=hashlib.sha256(raw).hexdigest(),
                archive_filename=name,
                outcome="no_memory",
                reason="no facts",
            )
        )
    with pytest.raises(MemoryError, match="VALIDATION_ERROR"):
        apply_patch(store, MemoryPatch(idempotency_key="collision", close_inbox=items))


def test_nested_invalid_ref_rejected(store):
    a = apply_patch(store, sample_patch())
    with pytest.raises(MemoryError, match="VALIDATION_ERROR"):
        read_memory(store, "mem://unexpected/document/" + a.id_map["new:d"])


def test_event_cannot_be_overwritten_and_destination_not_clobbered(store):
    a = apply_patch(store, sample_patch())
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute("UPDATE events SET summary='bad'")
    store.db.rollback()
    target = store.root / "L1/existing.md"
    target.write_bytes(
        (store.root / "L1/projects.md")
        .read_bytes()
        .replace(a.id_map["new:d"].encode(), b"55555555-5555-4555-8555-555555555555")
    )
    before = target.read_bytes()
    p = MemoryPatch(
        idempotency_key="move-conflict",
        documents=[
            dict(
                action="move",
                ref="mem://document/" + a.id_map["new:d"],
                path="L1/existing.md",
                expected_sha256=a.document_etags[a.id_map["new:d"]],
            )
        ],
    )
    with pytest.raises(MemoryError, match="CONFLICT"):
        apply_patch(store, p)
    assert target.read_bytes() == before
