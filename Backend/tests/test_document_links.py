import pytest

from mem.apply import apply_patch
from mem.documents import load_documents
from mem.errors import MemoryError
from mem.health import get_health
from mem.models import MemoryPatch, SearchRequest
from mem.read import read_memory
from mem.search import search_memory


def linked_patch(*, reciprocal=True):
    return MemoryPatch.model_validate(
        {
            "idempotency_key": "linked-documents",
            "topics": [{"ref": "new:topic", "title": "Related project"}],
            "sources": [
                {
                    "ref": "new:source",
                    "kind": "session",
                    "origin_ref": "session:links",
                    "excerpt": "L2 and L3 should be linked both ways.",
                }
            ],
            "documents": [
                {
                    "ref": "new:l2",
                    "layer": "L2",
                    "topic_refs": ["new:topic"],
                    "title": "Project context",
                    "path": "L2/context.md",
                    "markdown": "Shared link example",
                    "source_refs": ["new:source"],
                    "linked_document_refs": ["new:l3"],
                },
                {
                    "ref": "new:l3",
                    "layer": "L3",
                    "topic_refs": ["new:topic"],
                    "title": "Project summary",
                    "path": "L3/summary.md",
                    "markdown": "Shared link example",
                    "source_refs": ["new:source"],
                    "linked_document_refs": ["new:l2"] if reciprocal else [],
                },
            ],
        }
    )


def test_bidirectional_l2_l3_links_are_persisted_and_searchable(store):
    result = apply_patch(store, linked_patch())
    l2 = "mem://document/" + result.id_map["new:l2"]
    l3 = "mem://document/" + result.id_map["new:l3"]
    assert read_memory(store, l2).data["linked_document_refs"] == [l3]
    assert read_memory(store, l3).data["linked_document_refs"] == [l2]
    hits = search_memory(store, SearchRequest(query="Shared")).items
    assert {h.ref for h in hits} == {l2, l3}
    assert {h.ref: h.linked_document_refs for h in hits} == {
        l2: [l3],
        l3: [l2],
    }


def test_one_way_links_generate_reverse_read_links(store):
    result = apply_patch(store, linked_patch(reciprocal=False))
    l2 = "mem://document/" + result.id_map["new:l2"]
    l3 = "mem://document/" + result.id_map["new:l3"]
    assert read_memory(store, l2).data["related_document_refs"] == [l3]
    assert read_memory(store, l3).data["related_document_refs"] == [l2]
    assert read_memory(store, l3).data["linked_document_refs"] == [l2]
    assert store.db.execute("SELECT count(*) FROM operations").fetchone()[0] == 1


@pytest.mark.parametrize("duplicate_name", ["a.md", "zz.md"])
def test_duplicate_document_id_has_no_canonical_winner(store, duplicate_name):
    result = apply_patch(store, linked_patch(reciprocal=False))
    target = "mem://document/" + result.id_map["new:l3"]
    original = store.root / "L3/summary.md"
    duplicate = store.root / "L3" / duplicate_name
    duplicate.write_bytes(original.read_bytes())
    with pytest.raises(MemoryError, match="INDEX_INVALID"):
        load_documents(store)
    with pytest.raises(MemoryError, match="CONFLICT"):
        read_memory(store, target)
    with pytest.raises(MemoryError, match="CONFLICT"):
        apply_patch(
            store, MemoryPatch(
                idempotency_key="ambiguous-write",
                documents=[{
                    "action": "replace", "ref": target,
                    "layer": "L3", "topic_refs": [
                        "mem://topic/" + result.id_map["new:topic"]
                    ],
                    "title": "Changed", "path": "L3/summary.md",
                    "markdown": "Must not write",
                    "expected_sha256": read_memory(
                        store, "mem://document/" + result.id_map["new:l2"]
                    ).source_etag,
                }],
            )
        )
    report = get_health(store)
    issues = [i for i in report.issues if i["code"] == "DOCUMENT_ID_AMBIGUOUS"]
    assert {i["path"] for i in issues} == {
        "L3/summary.md", "L3/" + duplicate_name
    }
    hits = search_memory(store, SearchRequest(query="Shared")).items
    assert target not in {h.ref for h in hits}
    assert "mem://document/" + result.id_map["new:l2"] in {h.ref for h in hits}
    assert original.exists() and duplicate.exists()


def test_one_way_relationship_survives_document_move(store):
    result = apply_patch(store, linked_patch(reciprocal=False))
    l2 = "mem://document/" + result.id_map["new:l2"]
    l3 = "mem://document/" + result.id_map["new:l3"]
    etag = read_memory(store, l3).source_etag
    apply_patch(store, MemoryPatch(
        idempotency_key="move-linked",
        documents=[{
            "action": "move", "ref": l3, "path": "L3/moved.md",
            "expected_sha256": etag,
        }],
    ))
    assert read_memory(store, l3).data["path"] == "L3/moved.md"
    assert read_memory(store, l2).data["related_document_refs"] == [l3]
    assert read_memory(store, l3).data["related_document_refs"] == [l2]


@pytest.mark.parametrize("target", [
    "mem://event/55555555-5555-4555-8555-555555555555",
    "mem://archive/55555555-5555-4555-8555-555555555555",
    "mem://document/55555555-5555-4555-8555-555555555555",
    "new:l2",
])
def test_bad_document_link_rejected_before_prepare(store, target):
    payload = linked_patch(reciprocal=False).model_dump()
    payload["documents"][0]["related_refs"] = [target]
    payload["documents"][0]["linked_document_refs"] = None
    with pytest.raises(MemoryError):
        apply_patch(store, MemoryPatch.model_validate(payload))
    assert store.db.execute("SELECT count(*) FROM operations").fetchone()[0] == 0
    assert not (store.root / "L2/context.md").exists()


def test_external_link_target_deletion_does_not_hide_valid_document(store):
    result = apply_patch(store, linked_patch(reciprocal=False))
    l2 = "mem://document/" + result.id_map["new:l2"]
    l3 = "mem://document/" + result.id_map["new:l3"]
    (store.root / "L3/summary.md").unlink()
    assert read_memory(store, l2).data["path"] == "L2/context.md"
    assert read_memory(store, l2).data["related_document_refs"] == []
    assert any(
        i["code"] == "DOCUMENT_LINK_DANGLING"
        for i in get_health(store).issues
    )
    assert l2 in {
        hit.ref for hit in search_memory(store, SearchRequest(query="Shared")).items
    }
    assert l3 not in {
        hit.ref for hit in search_memory(store, SearchRequest(query="Shared")).items
    }


def test_source_free_documents_use_schema2_and_topic_is_l2_l3_only(store):
    patch = linked_patch(reciprocal=False)
    patch.sources = []
    for change in patch.documents:
        change.source_refs = []
    result = apply_patch(store, patch)
    l2 = "mem://document/" + result.id_map["new:l2"]
    l3 = "mem://document/" + result.id_map["new:l3"]
    raw_l2 = (store.root / "L2/context.md").read_text()
    raw_l3 = (store.root / "L3/summary.md").read_text()
    assert "schema_version: 2" in raw_l2
    assert "schema_version: 2" in raw_l3
    assert "related_refs:" in raw_l2
    assert "related_refs:" not in raw_l3
    assert read_memory(store, l2).data["related_document_refs"] == [l3]
    assert read_memory(store, l3).data["related_document_refs"] == [l2]
    topic = read_memory(
        store, "mem://topic/" + result.id_map["new:topic"]
    ).data
    assert set(topic["document_refs"]) == {l2, l3}
    assert "event_refs" not in topic
    assert "source_refs" not in read_memory(store, l2).data
