import pytest

from mem.apply import apply_patch
from mem.errors import MemoryError
from mem.index import rebuild_index
from mem.models import MemoryPatch, SearchRequest
from mem.search import search_memory

from .helpers import sample_patch


@pytest.mark.parametrize("query", ["өгөгдөл", "ҮР", "ёс", "SQLite smoke"])
def test_cyrillic_and_english_literal_search(store, query):
    a = apply_patch(store, sample_patch())
    hits = search_memory(store, SearchRequest(query=query)).items
    assert {h.ref for h in hits} == {"mem://document/" + a.id_map["new:d"]}
    assert not search_memory(store, SearchRequest(query="Огогдол")).items


def test_rebuild_from_markdown_and_l3(store):
    a = apply_patch(store, sample_patch())
    req = SearchRequest(query="smoke")
    before = {h.ref for h in search_memory(store, req).items}
    assert before == {
        "mem://document/" + a.id_map["new:d"],
        "mem://event/" + a.id_map["new:e"],
    }
    dbhash = store.db.execute("SELECT count(*) FROM events").fetchone()[0]
    store.index_path.unlink()
    rebuild_index(store)
    assert {h.ref for h in search_memory(store, req).items} == before
    assert store.db.execute("SELECT count(*) FROM events").fetchone()[0] == dbhash


def test_external_edit_visible_next_search(store):
    a = apply_patch(store, sample_patch())
    search_memory(store, SearchRequest(query="smoke"))
    path = store.root / "L3/projects.md"
    path.write_bytes(path.read_bytes() + "\nшинээр".encode())
    assert (
        search_memory(store, SearchRequest(query="шинээр")).items[0].ref
        == "mem://document/" + a.id_map["new:d"]
    )


def test_corrected_hit_is_not_presented_as_current(store):
    a = apply_patch(store, sample_patch())
    p = MemoryPatch(
        idempotency_key="correction",
        sources=[
            dict(
                ref="new:s",
                kind="session",
                origin_ref="session:2",
                excerpt="Actual outcome PASS, previous FAIL was incorrect",
            )
        ],
        events=[
            dict(
                ref="new:e",
                topic_refs=["mem://topic/" + a.id_map["new:t"]],
                kind="correction",
                summary="Actual outcome PASS",
                evidence_kind="tool_observed",
                source_refs=["new:s"],
                corrects_event_id="mem://event/" + a.id_map["new:e"],
            )
        ],
    )
    b = apply_patch(store, p)
    hit = search_memory(store, SearchRequest(query="FAIL")).items[0]
    assert hit.record_status == "corrected"
    assert hit.latest_correction_ref == "mem://event/" + b.id_map["new:e"]
    assert hit.effective_summary == "Actual outcome PASS"
    assert search_memory(store, SearchRequest(query="PASS")).items
    with pytest.raises(MemoryError, match="CONFLICT"):
        apply_patch(store, p.model_copy(update={"idempotency_key": "branch"}))


def test_query_syntax_is_literal(store):
    apply_patch(store, sample_patch())
    assert not search_memory(store, SearchRequest(query='" OR 1=1 --')).items
    assert not search_memory(store, SearchRequest(query="smoke OR nonexistent")).items


def test_invalid_source_isolated_without_hiding_valid_results(store):
    a = apply_patch(store, sample_patch())
    (store.root / "L3/bad.md").write_text("not a valid document")
    result = search_memory(store, SearchRequest(query="smoke"))
    assert "L3/bad.md" in result.invalid_sources
    assert "mem://document/" + a.id_map["new:d"] in {h.ref for h in result.items}


def test_filters_and_deleted_document(store):
    a = apply_patch(store, sample_patch())
    hits = search_memory(
        store,
        SearchRequest(query="smoke", layers=["L1"], topic_ids=[a.id_map["new:t"]]),
    ).items
    assert len(hits) == 1 and hits[0].layer == "L1"
    (store.root / "L3/projects.md").unlink()
    assert all(
        h.layer == "L1"
        for h in search_memory(store, SearchRequest(query="smoke")).items
    )
