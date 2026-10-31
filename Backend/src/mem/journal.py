"""Validate everything, then persist a recoverable operation before touching documents."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from .catalog import load_catalog, validate_document_links
from .documents import digest, now, parse_document, render_document
from .errors import MemoryError
from .models import ApplyResult
from .paths import resolve_safe_path
from .read import split_ref
from .shorthand import get_shorthand
from .sources import capture_source, reject_credentials


@dataclass
class PreparedOperation:
    operation_id: str
    result: ApplyResult


def request_fingerprint(patch):
    return digest(
        json.dumps(
            patch.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    )


def prepare_operation(store, patch):
    catalog = load_catalog(store)
    byid = dict(catalog.documents)
    opid = str(uuid4())
    ids = {}
    kinds = {}
    for kind, items in [
        ("topic", [t for t in patch.topics if t.action == "create"]),
        ("document", [d for d in patch.documents if d.action == "create"]),
        ("event", patch.events),
        ("source", patch.sources),
    ]:
        for item in items:
            if not item.ref.startswith("new:") or item.ref in ids:
                raise MemoryError("VALIDATION_ERROR", "Duplicate or invalid new ref")
            ids[item.ref] = str(uuid4())
            kinds[item.ref] = kind

    def resolve(ref, kind):
        if ref in ids:
            if kinds[ref] != kind:
                raise MemoryError("VALIDATION_ERROR", "Wrong ref type")
            return ids[ref]
        actual, ident = split_ref(ref)
        if actual != kind:
            raise MemoryError("VALIDATION_ERROR", "Wrong ref type")
        return ident

    topics = {r[0] for r in store.db.execute("SELECT id FROM topics")}
    topic_ops = []
    for t in patch.topics:
        ident = resolve(t.ref, "topic")
        reject_credentials(t.title)
        if t.action == "create":
            topics.add(ident)
        else:
            row = store.db.execute(
                "SELECT revision FROM topics WHERE id=?", (ident,)
            ).fetchone()
            if not row or row[0] != t.expected_revision:
                raise MemoryError("CONFLICT", "Topic changed")
        topic_ops.append(dict(id=ident, title=t.title, action=t.action))
    shorthand = get_shorthand(store)
    shorthand_ops = []
    changed_codes = set()
    for change in patch.shorthand:
        code = change.code
        if code in changed_codes:
            raise MemoryError("VALIDATION_ERROR", "Duplicate shorthand code")
        changed_codes.add(code)
        old = shorthand.get(code)
        if old != change.expected_expansion or (
            change.action == "remove" and old is None
        ):
            raise MemoryError("CONFLICT", "Shorthand meaning changed")
        reject_credentials(code + "\n" + (change.expansion or ""))
        if change.action == "set":
            shorthand[code] = change.expansion
        else:
            del shorthand[code]
        shorthand_ops.append(change.model_dump())

    sources = []
    inbox_snapshots = {}
    for draft in patch.sources:
        raw = None
        if draft.kind == "inbox":
            from .inbox import _read

            item = _read(store, draft.relative_path, draft.expected_sha256)
            inbox_snapshots[draft.relative_path] = (item, ids[draft.ref])
            raw = item.raw_bytes
        source = capture_source(draft, raw)
        source.source_id = ids[draft.ref]
        sources.append(asdict(source))
    known_sources = {r[0] for r in store.db.execute("SELECT id FROM sources")} | {
        s["source_id"] for s in sources
    }

    def refs(values, kind, known):
        result = [resolve(r, kind) for r in values]
        if len(result) != len(set(result)) or not set(result) <= known:
            raise MemoryError("VALIDATION_ERROR", "Unknown or duplicate linked ref")
        return result

    known_document_ids = set(byid) | {
        ids[d.ref] for d in patch.documents if d.action == "create"
    }
    future_documents = dict(byid)
    files = []
    docmeta = []
    etags = {}
    seen_docs = set()
    paths = set()
    for d in patch.documents:
        ident = resolve(d.ref, "document")
        if ident in seen_docs:
            raise MemoryError("VALIDATION_ERROR", "Document changed twice")
        seen_docs.add(ident)
        if ident in catalog.ambiguous_ids:
            raise MemoryError(
                "CONFLICT",
                "Ambiguous document ID",
                {"paths": catalog.ambiguous_ids[ident]},
            )
        previous = byid.get(ident)
        if d.action != "create" and (
            not previous or previous.sha256 != d.expected_sha256
        ):
            raise MemoryError("CONFLICT", "Document changed")
        layer = d.layer if d.action != "move" else previous.layer
        destination = resolve_safe_path(store.root, d.path, layer)
        if destination.suffix != ".md":
            raise MemoryError("VALIDATION_ERROR", "Markdown extension required")
        if d.action == "replace" and (
            d.path != previous.path or layer != previous.layer
        ):
            raise MemoryError("CONFLICT", "Use explicit move for path changes")
        touched = {destination}
        if previous:
            touched.add(resolve_safe_path(store.root, previous.path, previous.layer))
        for candidate in touched:
            for ancestor in candidate.parents:
                if ancestor == store.root:
                    break
                if ancestor.exists() and not ancestor.is_dir():
                    raise MemoryError("CONFLICT", "Parent path is a file")
            for other in paths:
                if (
                    candidate == other
                    or candidate.is_relative_to(other)
                    or other.is_relative_to(candidate)
                ):
                    raise MemoryError(
                        "VALIDATION_ERROR", "Conflicting canonical document paths"
                    )
        paths.update(touched)
        if d.action == "create" or (d.action == "move" and d.path != previous.path):
            if destination.exists():
                raise MemoryError("CONFLICT", "Destination exists")
        source_ids = refs(d.source_refs, "source", known_sources)
        if d.action == "move":
            raw = previous.raw
        else:
            requested_links = (
                d.related_refs if d.related_refs is not None
                else d.linked_document_refs
            )
            if requested_links is None:
                linked_ids = previous.linked_document_ids if previous else []
            else:
                for link_ref in requested_links:
                    if (
                        isinstance(link_ref, str)
                        and link_ref.startswith("mem://document/")
                        and link_ref[len("mem://document/"):]
                        in catalog.ambiguous_ids
                    ):
                        raise MemoryError("CONFLICT", "Ambiguous linked document ID")
                linked_ids = refs(
                    requested_links, "document", known_document_ids
                )
            raw = render_document(
                ident,
                layer,
                refs(d.topic_refs, "topic", topics),
                d.title,
                d.markdown,
                linked_document_ids=linked_ids,
            )
        future_documents[ident] = parse_document(raw, d.path, topics)
        before = previous.raw if previous and previous.path == d.path else None
        files.append((d.path, before, raw))
        if d.action == "move" and previous.path != d.path:
            files.append((previous.path, previous.raw, None))
        docmeta.append(
            dict(
                id=ident,
                before_path=previous.path if previous else None,
                source_ids=source_ids,
            )
        )
        etags[ident] = digest(raw)
    validate_document_links(
        catalog, list(future_documents.values()), changed_ids=seen_docs
    )
    events = []
    known_events = {r[0] for r in store.db.execute("SELECT id FROM events")}
    targets = {
        r[0]
        for r in store.db.execute(
            "SELECT corrects_event_id FROM events WHERE corrects_event_id IS NOT NULL"
        )
    }
    for e in patch.events:
        reject_credentials(e.summary + "\n" + e.details)
        target = resolve(e.corrects_event_id, "event") if e.corrects_event_id else None
        if target and (target not in known_events or target in targets):
            raise MemoryError(
                "CONFLICT", "Correction target missing or already corrected"
            )
        value = e.model_dump()
        value.update(
            id=ids[e.ref],
            topic_ids=refs(e.topic_refs, "topic", topics),
            source_ids=refs(e.source_refs, "source", known_sources),
            corrects_event_id=target,
            recorded_at=now(),
        )
        events.append(value)
        known_events.add(value["id"])
        if target:
            targets.add(target)
    archive_sources = []
    archive_names = set()
    closed_paths = set()
    closed_hashes = set()
    for completion in patch.close_inbox:
        from .archive import validate_filename
        from .inbox import _read

        item = _read(store, completion.relative_path, completion.expected_sha256)
        validate_filename(completion.archive_filename, completion.relative_path)
        if (
            Path(completion.archive_filename).stem.casefold() in archive_names
            or completion.relative_path in closed_paths
        ):
            raise MemoryError(
                "VALIDATION_ERROR", "Duplicate archive destination/source"
            )
        archive_names.add(Path(completion.archive_filename).stem.casefold())
        closed_paths.add(completion.relative_path)
        done = store.db.execute(
            "SELECT archive_ref FROM processed_sources WHERE sha256=?", (item.sha256,)
        ).fetchone()
        pending = store.db.execute(
            "SELECT 1 FROM operation_sources WHERE sha256=?", (item.sha256,)
        ).fetchone()
        if item.sha256 in closed_hashes:
            raise MemoryError(
                "SOURCE_ALREADY_PROCESSED", "Same raw content twice in one operation"
            )
        closed_hashes.add(item.sha256)
        if done or pending:
            raise MemoryError(
                "SOURCE_ALREADY_PROCESSED",
                "Source processed or pending",
                {"archive_ref": done[0] if done else None},
            )
        if completion.relative_path in inbox_snapshots:
            _, sid = inbox_snapshots[completion.relative_path]
        else:
            full_text = item.raw_bytes.decode("utf-8")
            reject_credentials(full_text)
            sid = str(uuid4())
            ids["inbox:" + completion.relative_path] = sid
            sources.append(
                dict(
                    source_id=sid,
                    kind="inbox",
                    origin_ref=completion.relative_path,
                    excerpt="",
                    sha256=item.sha256,
                    full_text=full_text,
                )
            )
        linked = any(sid in e["source_ids"] for e in events) or any(
            sid in d["source_ids"] for d in docmeta
        )
        if completion.outcome == "recorded" and not linked:
            raise MemoryError(
                "VALIDATION_ERROR", "Recorded source must support a change"
            )
        if completion.outcome == "no_memory" and (
            not completion.reason.strip() or linked
        ):
            raise MemoryError(
                "VALIDATION_ERROR", "no_memory requires reason and no linked memory"
            )
        archive_sources.append(
            dict(
                source_id=sid,
                relative_path=item.relative_path,
                sha256=item.sha256,
                raw=item.raw_bytes,
                archive_filename=completion.archive_filename,
                outcome=completion.outcome,
                reason=completion.reason,
            )
        )
    total = sum(len(b or b"") + len(a or b"") for _, b, a in files) + len(
        patch.model_dump_json().encode()
    )
    total += sum(len(a["raw"]) for a in archive_sources)
    if total > 50 * 1024 * 1024:
        raise MemoryError("VALIDATION_ERROR", "Patch exceeds 50 MiB")
    result = ApplyResult(
        operation_id=opid, state="PREPARED", id_map=ids, document_etags=etags
    )
    payload = dict(
        topics=topic_ops,
        shorthand=shorthand_ops,
        sources=sources,
        events=events,
        documents=docmeta,
        prepared_at=now(),
    )
    with store.db:
        store.db.execute(
            "INSERT INTO operations VALUES (?,?,?,?,?,?)",
            (
                opid,
                patch.idempotency_key,
                request_fingerprint(patch),
                json.dumps(payload, ensure_ascii=False),
                "PREPARED",
                result.model_dump_json(),
            ),
        )
        for n, (path, before, after) in enumerate(files):
            store.db.execute(
                "INSERT INTO operation_documents VALUES (?,?,?,?,?)",
                (opid, n, path, before, after),
            )
        for a in archive_sources:
            store.db.execute(
                "INSERT INTO operation_sources VALUES (?,?,?,?,?,?,?,?,NULL)",
                (
                    opid,
                    a["source_id"],
                    a["relative_path"],
                    a["sha256"],
                    a["raw"],
                    a["archive_filename"],
                    a["outcome"],
                    a["reason"],
                ),
            )
    return PreparedOperation(opid, result)
