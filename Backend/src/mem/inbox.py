from dataclasses import dataclass

from .documents import digest
from .errors import MemoryError
from .paths import resolve_safe_path


@dataclass
class InboxItem:
    relative_path: str
    size_bytes: int
    sha256: str
    raw_bytes: bytes


@dataclass
class InboxPage:
    items: list[dict]
    next_cursor: str | None


def _read(store, relative_path, expected_sha256=None):
    path = resolve_safe_path(store.root, relative_path, "L0/Inbox")
    if not path.is_file():
        raise MemoryError("NOT_FOUND", "Inbox file not found")
    if path.stat().st_size > 10 * 1024 * 1024:
        raise MemoryError("VALIDATION_ERROR", "Inbox exceeds 10 MiB")
    raw = path.read_bytes()
    if len(raw) > 10 * 1024 * 1024:
        raise MemoryError("VALIDATION_ERROR", "Inbox exceeds 10 MiB")
    try:
        raw.decode("utf-8")
    except UnicodeError:
        raise MemoryError("VALIDATION_ERROR", "Inbox must be UTF-8 text") from None
    sha = digest(raw)
    if expected_sha256 and sha != expected_sha256:
        raise MemoryError("CONFLICT", "Inbox changed")
    return InboxItem(relative_path, len(raw), sha, raw)


def read_inbox(store, relative_path, expected_sha256):
    with store.mutex:
        store.ensure_ready()
        return _read(store, relative_path, expected_sha256)


def list_inbox(store, cursor=None, limit=20):
    with store.mutex:
        store.ensure_ready()
        if not 1 <= limit <= 100:
            raise MemoryError("VALIDATION_ERROR", "Invalid limit")
        items = []
        for path in sorted((store.root / "L0/Inbox").rglob("*")):
            if path.is_file():
                rel = path.relative_to(store.root).as_posix()
                if cursor and rel <= cursor:
                    continue
                item = _read(store, rel)
                items.append(
                    dict(
                        relative_path=rel,
                        size_bytes=item.size_bytes,
                        sha256=item.sha256,
                    )
                )
                if len(items) > limit:
                    break
        return InboxPage(
            items[:limit],
            items[limit - 1]["relative_path"] if len(items) > limit else None,
        )
