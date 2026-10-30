import hashlib
import unicodedata
from dataclasses import asdict, dataclass
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

    def public(self):
        value = asdict(self)
        value.pop("raw")
        return value


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return datetime.now(UTC).isoformat()


def parse_document(raw: bytes, path: str, known_topics: set[str]) -> DocumentRecord:
    try:
        if len(raw) > 1024 * 1024:
            raise ValueError("size")
        text = raw.decode("utf-8")
        if not text.startswith("---\n"):
            raise ValueError("frontmatter")
        head, body = text[4:].split("\n---\n", 1)
        if any(
            isinstance(t, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken))
            for t in yaml.scan(head)
        ):
            raise ValueError("alias")
        meta = yaml.load(head, Loader=UniqueLoader)
        if not isinstance(meta, dict) or set(meta) != {
            "schema_version",
            "document_id",
            "layer",
            "topic_ids",
            "title",
            "updated_at",
        }:
            raise ValueError("fields")
        if meta["schema_version"] != 1:
            raise ValueError("schema")
        ident = str(UUID(meta["document_id"]))
        if meta["layer"] not in ("L1", "L2") or path.split("/")[0] != meta["layer"]:
            raise ValueError("layer")
        topics = meta["topic_ids"]
        if (
            not isinstance(topics, list)
            or not topics
            or any(str(UUID(t)) not in known_topics for t in topics)
        ):
            raise ValueError("topics")
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


def load_documents(store):
    known = {r[0] for r in store.db.execute("SELECT id FROM topics")}
    docs = []
    seen = set()
    for layer in ["L1", "L2"]:
        for path in sorted((store.root / layer).rglob("*.md")):
            rel = path.relative_to(store.root).as_posix()
            safe = resolve_safe_path(store.root, rel, layer)
            doc = parse_document(safe.read_bytes(), rel, known)
            if doc.document_id in seen:
                raise MemoryError(
                    "INDEX_INVALID", "Duplicate document ID", {"path": rel}
                )
            seen.add(doc.document_id)
            docs.append(doc)
    return docs


def render_document(ident, layer, topic_ids, title, body):
    from .sources import reject_credentials

    reject_credentials(title + "\n" + body)
    meta = dict(
        schema_version=1,
        document_id=ident,
        layer=layer,
        topic_ids=topic_ids,
        title=unicodedata.normalize("NFC", title),
        updated_at=now(),
    )
    raw = (
        "---\n"
        + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
        + "---\n"
        + unicodedata.normalize("NFC", body)
    ).encode()
    if len(raw) > 1024 * 1024:
        raise MemoryError("VALIDATION_ERROR", "Document exceeds 1 MiB")
    return raw
