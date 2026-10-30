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
    if relative_path == "L0/Inbox/.gitkeep":
        raise MemoryError("VALIDATION_ERROR", "Directory marker is not an Inbox source")
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
    """List regular Inbox files without requiring text decoding.

    Pagination is based on the final result's path rather than the look-ahead
    item, so nested paths cannot be skipped between pages.
    """
    with store.mutex:
        store.ensure_ready()
        if not 1 <= limit <= 100:
            raise MemoryError("VALIDATION_ERROR", "Invalid limit")
        items = []
        paths = sorted(
            (p.relative_to(store.root).as_posix(), p)
            for p in (store.root / "L0/Inbox").rglob("*")
            if p.is_file() or p.is_symlink()
        )
        for rel, path in paths:
            if rel == "L0/Inbox/.gitkeep" or (cursor and rel <= cursor):
                continue
            try:
                safe = resolve_safe_path(store.root, rel, "L0/Inbox")
                if not safe.is_file():
                    continue
                size = safe.stat().st_size
                if size > 10 * 1024 * 1024:
                    item = dict(
                        relative_path=rel,
                        size_bytes=size,
                        sha256=None,
                        status="too_large",
                    )
                else:
                    raw = safe.read_bytes()
                    try:
                        raw.decode("utf-8")
                        status = "ok"
                    except UnicodeError:
                        status = "not_utf8"
                    item = dict(
                        relative_path=rel,
                        size_bytes=len(raw),
                        sha256=digest(raw),
                        status=status,
                    )
            except (MemoryError, OSError):
                item = dict(
                    relative_path=rel,
                    size_bytes=None,
                    sha256=None,
                    status="unreadable",
                )
            items.append(item)
            if len(items) > limit:
                break
        has_more = len(items) > limit
        page = items[:limit]
        return InboxPage(
            page,
            page[-1]["relative_path"] if has_more else None,
        )
