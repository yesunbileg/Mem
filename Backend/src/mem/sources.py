import re
from dataclasses import dataclass
from uuid import uuid4

from .documents import digest
from .errors import MemoryError


@dataclass
class SourceRecord:
    source_id: str
    kind: str
    origin_ref: str
    excerpt: str
    sha256: str


def reject_credentials(text):
    if re.search(
        r"(?i)(?:password|api[_-]?key|access[_-]?token|secret)\s*[:=]\s*[\w/+=.-]{8,}|\b(?:ghp_|sk-)[A-Za-z0-9_-]{20,}",
        text,
    ):
        raise MemoryError(
            "VALIDATION_ERROR", "Credential-like content cannot be stored as memory"
        )


def capture_source(draft, raw_bytes):
    reject_credentials(draft.excerpt)
    raw = raw_bytes if draft.kind == "inbox" else draft.excerpt.encode()
    if raw is None:
        raise MemoryError("VALIDATION_ERROR", "Missing source bytes")
    return SourceRecord(
        str(uuid4()), draft.kind, draft.origin_ref, draft.excerpt, digest(raw)
    )
