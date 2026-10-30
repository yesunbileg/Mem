TOPIC = "11111111-1111-4111-8111-111111111111"
DOC = "22222222-2222-4222-8222-222222222222"
EVENT = "33333333-3333-4333-8333-333333333333"
CORRECTION = "44444444-4444-4444-8444-444444444444"


def seed_document(store):
    store.db.execute("INSERT INTO topics VALUES (?,?,1)", (TOPIC, "Mem"))
    store.db.commit()
    data = f'---\nschema_version: 1\ndocument_id: {DOC}\nlayer: L1\ntopic_ids: [{TOPIC}]\ntitle: Devices\nupdated_at: "2026-10-30T00:00:00+00:00"\n---\nӨгөгдөл Үр дүн Ёс SQLite smoke\n'.encode()
    (store.root / "L1/devices.md").write_bytes(data)
    return data


def sample_patch(key="write-1"):
    from mem.models import MemoryPatch

    return MemoryPatch.model_validate(
        dict(
            idempotency_key=key,
            topics=[dict(ref="new:t", title="Mem")],
            sources=[
                dict(
                    ref="new:s",
                    kind="session",
                    origin_ref="session:1/message:1",
                    excerpt="MCP smoke test FAIL observed",
                )
            ],
            documents=[
                dict(
                    ref="new:d",
                    layer="L1",
                    topic_refs=["new:t"],
                    title="Mem project",
                    path="L1/projects.md",
                    markdown="Өгөгдөл Үр дүн Ёс SQLite smoke",
                    source_refs=["new:s"],
                )
            ],
            events=[
                dict(
                    ref="new:e",
                    kind="test",
                    topic_refs=["new:t"],
                    summary="MCP smoke FAIL",
                    details="One test failed",
                    evidence_kind="tool_observed",
                    source_refs=["new:s"],
                )
            ],
        )
    )


def count_events(store):
    return store.db.execute("SELECT count(*) FROM events").fetchone()[0]
