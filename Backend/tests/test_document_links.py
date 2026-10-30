import pytest

from mem.apply import apply_patch
from mem.errors import MemoryError
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


def test_one_way_links_are_rejected_without_writes(store):
    with pytest.raises(MemoryError, match="VALIDATION_ERROR"):
        apply_patch(store, linked_patch(reciprocal=False))
    assert store.db.execute("SELECT count(*) FROM operations").fetchone()[0] == 0
    assert not (store.root / "L2/context.md").exists()
    assert not (store.root / "L3/summary.md").exists()
