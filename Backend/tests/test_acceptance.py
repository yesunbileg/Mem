import hashlib

from mem.apply import apply_patch
from mem.backup import create_backup, create_snapshot, restore_backup
from mem.index import rebuild_index
from mem.models import MemoryPatch, SearchRequest
from mem.read import read_memory
from mem.search import search_memory
from mem.store import open_store


def test_full_inbox_memory_correction_backup_restore(store, tmp_path):
    raw = "Хэрэглэгч Mem төсөлд Windows хүсэв.\r\nБодит smoke тест FAIL болсон.\r\n".encode()
    (store.root / "L0/Inbox/chat.md").write_bytes(raw)
    patch = MemoryPatch.model_validate(
        dict(
            idempotency_key="acceptance-1",
            topics=[dict(ref="new:t", title="Mem")],
            sources=[
                dict(
                    ref="new:s",
                    kind="inbox",
                    origin_ref="chat:1",
                    relative_path="L0/Inbox/chat.md",
                    expected_sha256=hashlib.sha256(raw).hexdigest(),
                    excerpt="Бодит smoke тест FAIL болсон.",
                )
            ],
            documents=[
                dict(
                    ref="new:d",
                    layer="L2",
                    topic_refs=["new:t"],
                    title="Mem зорилго",
                    path="L2/mem/context.md",
                    markdown="Mem төсөлд Windows дэмжлэг хүссэн.",
                    source_refs=["new:s"],
                )
            ],
            events=[
                dict(
                    ref="new:e",
                    kind="test",
                    topic_refs=["new:t"],
                    summary="Mem smoke FAIL",
                    evidence_kind="tool_observed",
                    source_refs=["new:s"],
                )
            ],
            close_inbox=[
                dict(
                    relative_path="L0/Inbox/chat.md",
                    expected_sha256=hashlib.sha256(raw).hexdigest(),
                    archive_filename="Mem-Windows-smoke-тест.md",
                    outcome="recorded",
                )
            ],
        )
    )
    result = apply_patch(store, patch)
    assert result.state == "DONE" and result.archive_status == "complete"
    source = read_memory(store, "mem://source/" + result.id_map["new:s"])
    assert source.data["text"].encode() == raw
    correction = MemoryPatch(
        idempotency_key="correct-test",
        sources=[
            dict(
                ref="new:s",
                kind="session",
                origin_ref="session:2/tool:1",
                excerpt="Corrected smoke result is PASS",
            )
        ],
        events=[
            dict(
                ref="new:e",
                kind="correction",
                topic_refs=["mem://topic/" + result.id_map["new:t"]],
                summary="Mem smoke PASS",
                evidence_kind="tool_observed",
                source_refs=["new:s"],
                corrects_event_id="mem://event/" + result.id_map["new:e"],
            )
        ],
    )
    corrected = apply_patch(store, correction)
    hits = search_memory(store, SearchRequest(query="FAIL")).items
    assert hits[0].record_status == "corrected"
    assert hits[0].effective_summary == "Mem smoke PASS"
    before = {h.ref for h in search_memory(store, SearchRequest(query="Mem")).items}
    store.index_path.unlink()
    rebuild_index(store)
    assert {
        h.ref for h in search_memory(store, SearchRequest(query="Mem")).items
    } == before
    create_snapshot(store)
    backup = tmp_path / "complete.zip"
    create_backup(store, backup)
    destination = tmp_path / "restored"
    assert restore_backup(backup, destination).ready
    with open_store(destination) as restored:
        chain = read_memory(restored, "mem://event/" + result.id_map["new:e"])
        assert chain.data["effective_event"]["id"] == corrected.id_map["new:e"]
        assert chain.data["original"]["summary"] == "Mem smoke FAIL"
        assert (
            read_memory(restored, "mem://source/" + result.id_map["new:s"])
            .data["text"]
            .encode()
            == raw
        )
        assert {
            h.ref for h in search_memory(restored, SearchRequest(query="Mem")).items
        } == before
        assert apply_patch(restored, patch).operation_id == result.operation_id
