import pytest

from mem.apply import apply_patch
from mem.errors import MemoryError
from mem.models import MemoryPatch, SearchRequest
from mem.read import read_memory
from mem.search import search_memory


def test_history_and_symbol_agnostic_abbreviations(store):
    patch = MemoryPatch.model_validate(
        {
            "idempotency_key": "history-and-aliases",
            "topics": [{"ref": "new:t", "title": "Memory work"}],
            "shorthand": [
                {"code": "$scp", "expansion": "stage commit push"},
                {"code": "&", "expansion": "and marker"},
                {"code": "#q", "expansion": "user question"},
            ],
            "sources": [
                {
                    "ref": "new:s",
                    "kind": "session",
                    "origin_ref": "session:history/1",
                    "excerpt": "The user asked for a complete L1 history.",
                }
            ],
            "events": [
                {
                    "ref": "new:proposal",
                    "kind": "proposal",
                    "topic_refs": ["new:t"],
                    "summary": "Proposed $scp and & in a workflow",
                    "details": "This is only a proposal, not a completed action.",
                    "evidence_kind": "user_reported",
                    "source_refs": ["new:s"],
                },
                {
                    "ref": "new:question",
                    "kind": "question",
                    "topic_refs": ["new:t"],
                    "summary": "#q about an unrelated x$scpy identifier",
                    "details": "A question is not evidence that execution happened.",
                    "evidence_kind": "user_reported",
                    "source_refs": ["new:s"],
                },
            ],
        }
    )
    applied = apply_patch(store, patch)
    assert apply_patch(store, patch).operation_id == applied.operation_id
    hits = search_memory(store, SearchRequest(query="commit")).items
    assert {h.ref for h in hits} == {
        "mem://event/" + applied.id_map["new:proposal"]
    }
    assert {
        h.ref for h in search_memory(store, SearchRequest(query="$scp")).items
    } == {h.ref for h in hits}
    assert {
        h.ref for h in search_memory(store, SearchRequest(query="&")).items
    } == {h.ref for h in hits}
    question = read_memory(
        store, "mem://event/" + applied.id_map["new:question"]
    ).data["original"]
    assert question["kind"] == "question"
    proposal = read_memory(
        store, "mem://event/" + applied.id_map["new:proposal"]
    ).data["original"]
    assert proposal["kind"] == "proposal"


def test_shorthand_change_requires_previous_meaning_and_reindexes(store):
    base = MemoryPatch(
        idempotency_key="codes-1",
        topics=[{"ref": "new:t", "title": "Shorthand test"}],
        sources=[
            {
                "ref": "new:s",
                "kind": "session",
                "origin_ref": "session:aliases",
                "excerpt": "Short code example",
            }
        ],
        shorthand=[{"code": "scp", "expansion": "stage commit push"}],
        events=[
            {
                "ref": "new:e",
                "kind": "conversation",
                "topic_refs": ["new:t"],
                "summary": "Used scp as a demonstration",
                "evidence_kind": "user_reported",
                "source_refs": ["new:s"],
            }
        ],
    )
    apply_patch(store, base)
    assert search_memory(store, SearchRequest(query="push")).items

    with pytest.raises(MemoryError, match="CONFLICT"):
        apply_patch(
            store,
            MemoryPatch(
                idempotency_key="codes-conflict",
                shorthand=[{"code": "scp", "expansion": "a new meaning"}],
            ),
        )

    apply_patch(
        store,
        MemoryPatch(
            idempotency_key="codes-2",
            shorthand=[
                {
                    "action": "remove",
                    "code": "scp",
                    "expected_expansion": "stage commit push",
                }
            ],
        ),
    )
    assert not search_memory(store, SearchRequest(query="push")).items
    assert search_memory(store, SearchRequest(query="scp")).items
