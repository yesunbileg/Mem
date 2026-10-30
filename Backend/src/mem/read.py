import json
from dataclasses import asdict
from uuid import UUID

from .documents import digest, load_documents
from .errors import MemoryError
from .events import read_event_chain
from .models import ReadResult


def split_ref(ref):
    try:
        from urllib.parse import urlsplit

        value = urlsplit(ref)
        if (
            value.scheme != "mem"
            or value.netloc not in ("topic", "document", "event", "source")
            or value.query
            or value.fragment
            or value.path.count("/") != 1
        ):
            raise ValueError()
        return value.netloc, str(UUID(value.path[1:]))
    except (ValueError, AttributeError):
        raise MemoryError("VALIDATION_ERROR", "Invalid memory ref") from None


def read_memory(store, ref):
    with store.mutex:
        store.ensure_ready()
        kind, ident = split_ref(ref)
        if kind == "document":
            doc = next(
                (d for d in load_documents(store, tolerate_invalid=True) if d.document_id == ident), None
            )
            if not doc:
                raise MemoryError("NOT_FOUND", "Document not found")
            return ReadResult(
                ref=ref, kind=kind, data=doc.public(), source_etag=doc.sha256
            )
        if kind == "event":
            data = asdict(read_event_chain(store, ident))
        elif kind == "topic":
            row = store.db.execute(
                "SELECT * FROM topics WHERE id=?", (ident,)
            ).fetchone()
            if not row:
                raise MemoryError("NOT_FOUND", "Topic not found")
            data = dict(row)
            data["document_refs"] = [
                "mem://document/" + d.document_id
                for d in load_documents(store, tolerate_invalid=True)
                if ident in d.topic_ids
            ]
            data["event_refs"] = [
                "mem://event/" + r[0]
                for r in store.db.execute(
                    "SELECT event_id FROM event_topics WHERE topic_id=?", (ident,)
                )
            ]
        else:
            row = store.db.execute(
                "SELECT * FROM sources WHERE id=?", (ident,)
            ).fetchone()
            if not row:
                raise MemoryError("NOT_FOUND", "Source not found")
            data = dict(row)
        return ReadResult(
            ref=ref,
            kind=kind,
            data=data,
            source_etag=digest(
                json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
            ),
        )
