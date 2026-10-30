import hashlib
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import yaml

from .errors import MemoryError
from .paths import resolve_safe_path


class UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    result = {}
    for k, v in node.value:
        key = loader.construct_object(k, deep=deep)
        if not isinstance(key, str) or key in result:
            raise ValueError("duplicate/invalid key")
        result[key] = loader.construct_object(v, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


@dataclass
class DocumentRecord:
    document_id: str
    layer: str
    topic_ids: list[str]
    title: str
    updated_at: str
    path: str
    markdown: str
    sha256: str
    raw: bytes
    linked_document_ids: list[str] = field(default_factory=list)

    def public(self):
        value = asdict(self)
        value.pop("raw")
        value["linked_document_refs"] = [
            "mem://document/" + ident for ident in value.pop("linked_document_ids")
        ]
        return value


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return datetime.now(UTC).isoformat()


def parse_document(raw: bytes, path: str, known_topics: set[str]) -> DocumentRecord:
    try:
        if len(raw) > 1024 * 1024:
            raise ValueError("size")
        text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        if not text.startswith("---\n"):
            raise ValueError("frontmatter")
        head, body = text[4:].split("\n---\n", 1)
        if any(
            isinstance(t, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken))
            for t in yaml.scan(head)
        ):
            raise ValueError("alias")
        meta = yaml.load(head, Loader=UniqueLoader)
        if not isinstance(meta, dict) or not {
            "schema_version",
            "document_id",
            "layer",
            "topic_ids",
            "title",
            "updated_at",
        } <= set(meta):
            raise ValueError("fields")
        if meta["schema_version"] not in (1, 2):
            raise ValueError("schema")
        ident = str(UUID(meta["document_id"]))
        if meta["layer"] not in ("L3", "L2") or path.split("/")[0] != meta["layer"]:
            raise ValueError("layer")
        topics = meta["topic_ids"]
        if (
            not isinstance(topics, list)
            or not topics
            or any(str(UUID(t)) not in known_topics for t in topics)
        ):
            raise ValueError("topics")
        if meta["schema_version"] == 2:
            authored = meta.get("related_refs", [])
            if not isinstance(authored, list):
                raise ValueError("links")
            links = []
            for ref in authored:
                if not isinstance(ref, str) or not ref.startswith("mem://document/"):
                    raise ValueError("link type")
                ident = ref[len("mem://document/"):]
                if str(UUID(ident)) != ident:
                    raise ValueError("link ID")
                links.append(ident)
        else:
            links = meta.get("linked_document_ids", [])
        if (
            not isinstance(links, list)
            or len(set(links)) != len(links)
            or any(not isinstance(item, str) or str(UUID(item)) != item for item in links)
        ):
            raise ValueError("links")
        if not isinstance(meta["title"], str) or not meta["title"].strip():
            raise ValueError("title")
        updated = meta["updated_at"]
        if (
            not isinstance(updated, str)
            or datetime.fromisoformat(updated).tzinfo is None
        ):
            raise ValueError("time")
        return DocumentRecord(
            ident,
            meta["layer"],
            topics,
            meta["title"],
            updated,
            path,
            body,
            digest(raw),
            raw,
            links,
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        yaml.YAMLError,
        UnicodeError,
        AttributeError,
    ):
        raise MemoryError(
            "INDEX_INVALID", "Invalid canonical document", {"path": path}
        ) from None


def load_documents(store, *, tolerate_invalid=False, include_issues=False):
    """Compatibility adapter backed by the same duplicate-safe document catalog."""
    from .catalog import load_catalog

    catalog = load_catalog(store)
    if catalog.issues and not tolerate_invalid:
        raise MemoryError(
            "INDEX_INVALID",
            "Invalid canonical document catalog",
            {"issues": catalog.issues},
        )
    documents = sorted(catalog.documents.values(), key=lambda d: d.path)
    if include_issues:
        return documents, catalog.issues
    return documents


def render_document(ident, layer, topic_ids, title, body, linked_document_ids=None):
    from .sources import reject_credentials

    reject_credentials(title + "\n" + body)
    meta = dict(
        schema_version=2,
        document_id=ident,
        layer=layer,
        topic_ids=topic_ids,
        title=unicodedata.normalize("NFC", title),
        updated_at=now(),
    )
    if linked_document_ids:
        meta["related_refs"] = [
            "mem://document/" + ident for ident in linked_document_ids
        ]
    raw = (
        "---\n"
        + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
        + "---\n"
        + unicodedata.normalize("NFC", body)
    ).encode()
    if len(raw) > 1024 * 1024:
        raise MemoryError("VALIDATION_ERROR", "Document exceeds 1 MiB")
    return raw
