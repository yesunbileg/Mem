"""Regression tests for self-contained schema-v2 L1 history."""

import hashlib
import sqlite3
from importlib.resources import files

import pytest

from mem.apply import apply_patch
from mem.errors import MemoryError
from mem.models import MemoryPatch, SearchRequest
from mem.read import read_memory
from mem.search import search_memory
from mem.store import open_store


def test_full_history_keeps_speaker_source_and_immutable_correction(store):
    patch = MemoryPatch.model_validate({
        "idempotency_key": "v2-conversation",
        "sources": [
            {"ref": "new:s1", "kind": "session", "origin_ref": "session:1",
             "excerpt": "User asked if the deployment was finished. It was only suggested."},
            {"ref": "new:s2", "kind": "session", "origin_ref": "session:2",
             "excerpt": "Assistant did not run anything. It was a proposal."},
        ],
        "events": [
            {"ref": "new:e1", "kind": "question", "speaker": "user",
             "occurred_at": "2026-10-30T09:00:00+08:00",
             "summary": "Is deployment complete?", "evidence_kind": "user_reported",
             "source_refs": ["new:s1"]},
            {"ref": "new:e2", "kind": "proposal", "speaker": "assistant",
             "summary": "Suggested checking deployment, did not execute",
             "evidence_kind": "user_reported", "source_refs": ["new:s2"]},
            {"ref": "new:e3", "kind": "correction", "speaker": "user",
             "summary": "Clarified that work has not started",
             "evidence_kind": "user_reported", "source_refs": ["new:s1"],
             "corrects_event_id": "new:e1"},
        ],
    })
    result = apply_patch(store, patch)
    assert apply_patch(store, patch).id_map == result.id_map
    assert store.db.execute("PRAGMA user_version").fetchone()[0] == 2
    assert store.db.execute("SELECT count(*) FROM event_topics").fetchone()[0] == 0
    assert store.db.execute("SELECT count(*) FROM events").fetchone()[0] == 3
    question = read_memory(store, "mem://event/" + result.id_map["new:e1"]).data
    assert question["original"]["speaker"] == "user"
    assert question["original"]["kind"] == "question"
    assert question["original"]["occurred_at"] == "2026-10-30T09:00:00+08:00"
    assert question["effective_event"]["kind"] == "correction"
    assert not store.db.execute("SELECT 1 FROM events WHERE kind='action'").fetchone()
    source = read_memory(store, "mem://source/" + result.id_map["new:s2"]).data
    assert "did not run anything" in source["full_text"]
    assert any(
        h.ref == "mem://source/" + result.id_map["new:s2"]
        for h in search_memory(store, SearchRequest(query="anything")).items
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute(
            "UPDATE events SET summary=? WHERE id=?",
            ("changed", result.id_map["new:e1"]),
        )


def test_archived_inbox_text_is_readable_without_the_zip(store):
    raw = b"User: I proposed a change; no command has been executed.\n"
    inbox = store.root / "L0/Inbox/chat-example.md"
    inbox.write_bytes(raw)
    h = hashlib.sha256(raw).hexdigest()
    patch = MemoryPatch.model_validate({
        "idempotency_key": "full-inbox-evidence",
        "sources": [{"ref": "new:source", "kind": "inbox",
                     "origin_ref": "inbox:chat-example.md",
                     "relative_path": "L0/Inbox/chat-example.md",
                     "expected_sha256": h}],
        "events": [{"ref": "new:event", "kind": "conversation",
                    "summary": "Proposal, not an executed action",
                    "evidence_kind": "user_reported",
                    "source_refs": ["new:source"]}],
        "close_inbox": [{
            "relative_path": "L0/Inbox/chat-example.md",
            "expected_sha256": h,
            "archive_filename": "chat-example.md",
            "outcome": "recorded",
        }],
    })
    result = apply_patch(store, patch)
    assert not inbox.exists()
    archives = list((store.root / "L0/Archive").rglob("*.zip"))
    assert len(archives) == 1
    archives[0].unlink()
    evidence = read_memory(store, "mem://source/" + result.id_map["new:source"]).data
    assert evidence["full_text"].encode() == raw
    assert evidence["sha256"] == h
    assert search_memory(store, SearchRequest(query="executed")).items


def test_v1_sqlite_is_readable_and_never_auto_upgraded(tmp_path):
    root = tmp_path / "v1"
    (root / "L1").mkdir(parents=True)
    with sqlite3.connect(root / "L1/history.sqlite3") as db:
        db.executescript(
            files("mem").joinpath("migrations/001_initial.sql").read_text()
        )
    with open_store(root) as store:
        assert store.schema_version == 1
        with pytest.raises(MemoryError, match="SCHEMA_UNSUPPORTED"):
            apply_patch(store, MemoryPatch(idempotency_key="no-auto-upgrade"))
        assert store.db.execute("PRAGMA user_version").fetchone()[0] == 1
