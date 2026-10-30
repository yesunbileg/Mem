import hashlib

import pytest

from mem.apply import apply_patch
from mem.errors import MemoryError
from mem.models import MemoryPatch
from mem.read import read_memory

from .helpers import count_events, sample_patch


def test_apply_is_idempotent(store):
    p = sample_patch()
    a = apply_patch(store, p)
    b = apply_patch(store, p)
    assert a.operation_id == b.operation_id
    assert a.id_map == b.id_map
    assert count_events(store) == 1
    r = read_memory(store, "mem://event/" + a.id_map["new:e"])
    assert r.data["original"]["occurred_at"] is None
    assert (
        read_memory(store, "mem://source/" + a.id_map["new:s"]).data["excerpt"]
        == "MCP smoke test FAIL observed"
    )
    assert a.state == "DONE"


def replacement(result, key="replace"):
    return MemoryPatch.model_validate(
        dict(
            idempotency_key=key,
            sources=[
                dict(
                    ref="new:s",
                    kind="session",
                    origin_ref="session:2",
                    excerpt="User changed project goal",
                )
            ],
            documents=[
                dict(
                    action="replace",
                    ref="mem://document/" + result.id_map["new:d"],
                    layer="L3",
                    topic_refs=["mem://topic/" + result.id_map["new:t"]],
                    title="New goal",
                    path="L3/projects.md",
                    markdown="Шинэ зорилго",
                    expected_sha256=result.document_etags[result.id_map["new:d"]],
                    source_refs=["new:s"],
                )
            ],
        )
    )


def test_old_document_bytes_preserved(store):
    a = apply_patch(store, sample_patch())
    old = (store.root / "L3/projects.md").read_bytes()
    apply_patch(store, replacement(a))
    row = store.db.execute(
        "SELECT before_bytes FROM document_revisions WHERE before_bytes IS NOT NULL"
    ).fetchone()
    assert row[0] == old
    assert "Шинэ зорилго" in (store.root / "L3/projects.md").read_text()


def test_changed_etag_does_not_overwrite(store):
    a = apply_patch(store, sample_patch())
    p = store.root / "L3/projects.md"
    p.write_bytes(p.read_bytes() + b"\nmanual edit")
    changed = p.read_bytes()
    with pytest.raises(MemoryError, match="CONFLICT"):
        apply_patch(store, replacement(a))
    assert p.read_bytes() == changed
    assert count_events(store) == 1


def test_same_key_different_body_conflicts(store):
    apply_patch(store, sample_patch())
    p = sample_patch()
    p.events[0].summary = "Different"
    with pytest.raises(MemoryError, match="IDEMPOTENCY_CONFLICT"):
        apply_patch(store, p)


def test_validation_has_no_partial_writes(store):
    p = sample_patch()
    p.documents[0].topic_refs = ["mem://topic/77777777-7777-4777-8777-777777777777"]
    with pytest.raises(MemoryError):
        apply_patch(store, p)
    assert list((store.root / "L3").iterdir()) == []
    assert count_events(store) == 0
    assert store.db.execute("SELECT count(*) FROM topics").fetchone()[0] == 0
    assert store.db.execute("SELECT count(*) FROM operations").fetchone()[0] == 0


def test_move_retains_identity_and_conflicting_destination_fails(store):
    a = apply_patch(store, sample_patch())
    ident = a.id_map["new:d"]
    old = (store.root / "L3/projects.md").read_bytes()
    p = MemoryPatch(
        idempotency_key="move",
        documents=[
            dict(
                action="move",
                ref="mem://document/" + ident,
                path="L3/төслүүд.md",
                expected_sha256=hashlib.sha256(old).hexdigest(),
            )
        ],
    )
    apply_patch(store, p)
    assert read_memory(store, "mem://document/" + ident).data["path"] == "L3/төслүүд.md"
    assert not (store.root / "L3/projects.md").exists()
    assert (store.root / "L3/төслүүд.md").read_bytes() == old
