"""Single canonical view of L2/L3 files.

Never pick an arbitrary winner for a duplicated document UUID.  Public links
are derived from authored outgoing links and reverse links in this catalog.
"""

from dataclasses import dataclass, field

from .documents import DocumentRecord, parse_document
from .errors import MemoryError
from .paths import resolve_safe_path


@dataclass
class DocumentCatalog:
    documents: dict[str, DocumentRecord] = field(default_factory=dict)
    ambiguous_ids: dict[str, list[str]] = field(default_factory=dict)
    issues: list[dict] = field(default_factory=list)


def load_catalog(store):
    known = {r[0] for r in store.db.execute("SELECT id FROM topics")}
    groups = {}
    issues = []
    for layer in ("L3", "L2"):
        for path in sorted((store.root / layer).rglob("*.md")):
            rel = path.relative_to(store.root).as_posix()
            try:
                safe = resolve_safe_path(store.root, rel, layer)
                doc = parse_document(safe.read_bytes(), rel, known)
                groups.setdefault(doc.document_id, []).append(doc)
            except (MemoryError, OSError) as exc:
                issues.append(
                    dict(
                        code=getattr(exc, "code", "IO_ERROR"),
                        severity="error",
                        path=rel,
                        message=getattr(exc, "message", "Unable to read document"),
                    )
                )
    ambiguous = {}
    documents = {}
    for ident, group in groups.items():
        if len(group) == 1:
            documents[ident] = group[0]
        else:
            paths = sorted(doc.path for doc in group)
            ambiguous[ident] = paths
            for path in paths:
                issues.append(
                    dict(
                        code="DOCUMENT_ID_AMBIGUOUS",
                        severity="error",
                        path=path,
                        document_id=ident,
                        conflicting_paths=paths,
                        message="Multiple canonical files use this document ID",
                    )
                )

    # External deletion makes an outgoing link dangling. Do not hide the
    # surviving document or block access to unrelated canonical documents.
    for document in documents.values():
        for target in document.linked_document_ids:
            if target not in documents:
                issues.append(
                    dict(
                        code="DOCUMENT_LINK_DANGLING",
                        severity="error",
                        path=document.path,
                        document_id=document.document_id,
                        target_ref="mem://document/" + target,
                        message="Document link target is missing or ambiguous",
                    )
                )
    return DocumentCatalog(documents, ambiguous, issues)


def require_document(catalog, document_id):
    if document_id in catalog.ambiguous_ids:
        raise MemoryError(
            "CONFLICT",
            "Ambiguous document ID",
            {"paths": catalog.ambiguous_ids[document_id]},
        )
    doc = catalog.documents.get(document_id)
    if doc is None:
        raise MemoryError("NOT_FOUND", "Document not found")
    return doc


def related_document_refs(catalog, document_id):
    doc = require_document(catalog, document_id)
    connected = set(doc.linked_document_ids)
    connected.update(
        other.document_id
        for other in catalog.documents.values()
        if document_id in other.linked_document_ids
    )
    return ["mem://document/" + ident for ident in sorted(connected) if ident in catalog.documents]


def validate_document_links(catalog, proposed, *, changed_ids=None):
    """Check links against the prospective final catalog, before PREPARED.

    Existing externally damaged links do not block unrelated changes.
    """
    final = dict(catalog.documents)
    for doc in proposed:
        if doc.document_id in catalog.ambiguous_ids:
            raise MemoryError("CONFLICT", "Ambiguous document ID")
        final[doc.document_id] = doc
    changed = changed_ids if changed_ids is not None else {d.document_id for d in proposed}
    for ident in changed:
        doc = final[ident]
        for target_id in doc.linked_document_ids:
            if target_id in catalog.ambiguous_ids:
                raise MemoryError("CONFLICT", "Ambiguous linked document ID")
            target = final.get(target_id)
            if target is None or target.document_id == ident or target.layer == doc.layer:
                raise MemoryError("VALIDATION_ERROR", "Invalid L2/L3 link target")
            if not set(target.topic_ids).intersection(doc.topic_ids):
                raise MemoryError("VALIDATION_ERROR", "Linked documents must share a topic")
