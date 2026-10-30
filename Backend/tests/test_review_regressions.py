"""Independent whole-branch review regressions: accepted input must not corrupt readiness."""

import hashlib

import pytest

from mem.apply import apply_patch
from mem.backup import create_backup, restore_backup
from mem.errors import MemoryError
from mem.models import MemoryPatch
from mem.read import read_memory
from mem.store import open_store

from .helpers import sample_patch


def test_backup_keeps_mem_prefix_documents_and_inbox(store, tmp_path):
    p = sample_patch()
    p.documents[0].path = "L3/.mem-notes.md"
    a = apply_patch(store, p)
    (store.root / "L0/Inbox/.mem-user-notes.md").write_bytes(b"user raw")
    backup = tmp_path / "full.zip"
    manifest = create_backup(store, backup)
    assert "L3/.mem-notes.md" in manifest.files
    assert "L0/Inbox/.mem-user-notes.md" in manifest.files
    target = tmp_path / "restored"
    restore_backup(backup, target)
    with open_store(target) as s:
        assert (
            read_memory(s, "mem://document/" + a.id_map["new:d"]).data["title"]
            == "Mem project"
        )
        assert (target / "L0/Inbox/.mem-user-notes.md").read_bytes() == b"user raw"


@pytest.mark.parametrize(
    "second", ["L3/./projects.md", "L3//projects.md", "L3/projects.md/child.md"]
)
def test_path_alias_and_parent_conflicts_rejected_before_prepare(store, second):
    p = sample_patch()
    p.documents.append(
        p.documents[0].model_copy(
            update={"ref": "new:other", "path": second, "markdown": "different"}
        )
    )
    with pytest.raises(MemoryError):
        apply_patch(store, p)
    assert store.db.execute("SELECT count(*) FROM operations").fetchone()[0] == 0
    assert not list((store.root / "L3").iterdir())


def test_archive_checks_derived_zip_name_not_input_extension(store):
    closes = []
    for i, ext in enumerate(["md", "txt"]):
        raw = str(i).encode()
        path = f"L0/Inbox/{i}.{ext}"
        (store.root / path).write_bytes(raw)
        closes.append(
            dict(
                relative_path=path,
                expected_sha256=hashlib.sha256(raw).hexdigest(),
                archive_filename=f"Same-topic.{ext}",
                outcome="no_memory",
                reason="no new facts",
            )
        )
    with pytest.raises(MemoryError, match="VALIDATION_ERROR"):
        apply_patch(store, MemoryPatch(idempotency_key="same-zip", close_inbox=closes))
    assert store.db.execute("SELECT count(*) FROM operations").fetchone()[0] == 0


def test_old_partial_inbox_evidence_resolves_after_later_archive(store):
    raw = b"Actual test result FAIL, other work still pending"
    sha = hashlib.sha256(raw).hexdigest()
    path = "L0/Inbox/partial.md"
    (store.root / path).write_bytes(raw)
    data = sample_patch().model_dump()
    data["documents"] = []
    data["sources"] = [
        dict(
            ref="new:s",
            kind="inbox",
            origin_ref=path,
            relative_path=path,
            expected_sha256=sha,
        )
    ]
    a = MemoryPatch.model_validate(data)
    first = apply_patch(store, a)
    topic = "mem://topic/" + first.id_map["new:t"]
    b = MemoryPatch(
        idempotency_key="finish-partial",
        sources=[
            dict(
                ref="new:s",
                kind="inbox",
                origin_ref=path,
                relative_path=path,
                expected_sha256=sha,
            )
        ],
        events=[
            dict(
                ref="new:e",
                kind="result",
                topic_refs=[topic],
                summary="Other work finished",
                evidence_kind="user_reported",
                source_refs=["new:s"],
            )
        ],
        close_inbox=[
            dict(
                relative_path=path,
                expected_sha256=sha,
                archive_filename="Project-test-and-work.md",
                outcome="recorded",
            )
        ],
    )
    apply_patch(store, b)
    old_source = read_memory(store, "mem://source/" + first.id_map["new:s"])
    assert old_source.data["archive_ref"] is not None
    assert old_source.data["text"].encode() == raw
    assert not (store.root / path).exists()


def test_whitespace_title_rejected_without_invalidating_store(store):
    p = sample_patch()
    p.documents[0].title = " "
    with pytest.raises((MemoryError, ValueError)):
        apply_patch(store, p)
    assert store.db.execute("SELECT count(*) FROM operations").fetchone()[0] == 0
    assert not list((store.root / "L3").iterdir())
    assert apply_patch(store, sample_patch(key="valid")).state == "DONE"


@pytest.mark.parametrize(
    "limit,value",
    [("MAX_BACKUP_BYTES", 1024), ("MAX_BACKUP_MEMBERS", 2), ("MAX_MANIFEST_BYTES", 8)],
)
def test_backup_creator_enforces_same_limits_as_restore(
    store, tmp_path, monkeypatch, limit, value
):
    import mem.backup as b

    monkeypatch.setattr(b, limit, value, raising=False)
    (store.root / "L0/Inbox/notes.md").write_text("user raw")
    destination = tmp_path / "limited.zip"
    with pytest.raises(MemoryError, match="VALIDATION_ERROR"):
        create_backup(store, destination)
    assert not destination.exists()
