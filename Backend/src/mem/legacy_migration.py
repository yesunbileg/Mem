"""Offline, non-destructive migration from the original L1 Markdown/L3 SQLite layout.

The original store is never modified. A verified new store is published by a
single directory rename, so interruption cannot leave a half-migrated result.
"""

import hashlib
import os
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from .documents import parse_document
from .errors import MemoryError
from .locking import acquire_lock
from .paths import resolve_safe_path
from .recovery import fsync_directory


def _hash(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _legacy_files(root):
    """Reject links, retain every file under the four legacy data areas."""
    files = []
    for area in ("L0/Inbox", "L0/Archive", "L1", "L2"):
        base = root / area
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise MemoryError(
                    "VALIDATION_ERROR", "Symlink in legacy data", {"path": relative}
                )
            if path.is_dir():
                continue
            if not path.is_file():
                raise MemoryError(
                    "VALIDATION_ERROR", "Unsupported legacy item", {"path": relative}
                )
            resolve_safe_path(root, relative, area)
            files.append((relative, _hash(path)))
    return files


def _convert_old_document(raw, relative, topic_ids):
    """Change only the level key, preserving body, metadata and line endings."""
    converted, matches = re.subn(
        rb"(?m)^layer:[ \t]*(?:L1|'L1'|\"L1\")[ \t]*(?=\r?$)",
        b"layer: L3",
        raw,
        count=1,
    )
    if matches != 1:
        raise MemoryError(
            "INDEX_INVALID", "Expected legacy L1 frontmatter", {"path": relative}
        )
    new_rel = "L3/" + relative.removeprefix("L1/")
    parse_document(converted, new_rel, topic_ids)
    return converted


def migrate_legacy_store(source, destination):
    """Build the new layout alongside an old store, without touching the old one.

    Source must not be served by any MCP process. Destination must not exist.
    A SQLite online backup captures WAL data; the source file lock excludes
    cooperative writers. Source hashes are rechecked before atomic publication.
    """
    source = Path(source).absolute()
    destination = Path(destination).absolute()
    if source.is_symlink() or not source.is_dir():
        raise MemoryError("VALIDATION_ERROR", "Legacy source must be a real directory")
    if destination == source or source in destination.parents or destination in source.parents:
        raise MemoryError(
            "VALIDATION_ERROR", "Destination must be outside the legacy store"
        )
    if destination.exists() or destination.is_symlink():
        raise MemoryError("CONFLICT", "Migration destination must not exist")
    if (source / "L1/history.sqlite3").exists():
        raise MemoryError("CONFLICT", "Mixed legacy and new store layouts")
    if (source / "Backend/.state/store.lock").is_symlink():
        raise MemoryError("VALIDATION_ERROR", "Unsafe legacy lock path")
    old_db = source / "L3/history.sqlite3"
    if not old_db.is_file():
        old_db = source / "L3/history.snapshot.sqlite3"
    if not old_db.is_file() or old_db.is_symlink():
        raise MemoryError(
            "NOT_FOUND", "Legacy L3 database or snapshot not found"
        )
    lockdir = source / "Backend/.state"
    lockdir.mkdir(parents=True, exist_ok=True)
    lock = acquire_lock(lockdir / "store.lock")
    stage = None
    try:
        inventory = _legacy_files(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".mem-migrate-", dir=destination.parent))
        for area in ("L0/Inbox", "L0/Archive", "L1", "L2", "L3", "Backend/.state"):
            (stage / area).mkdir(parents=True, exist_ok=True)

        db_out = stage / "L1/history.sqlite3"
        with closing(sqlite3.connect(old_db.as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise MemoryError("SCHEMA_UNSUPPORTED", "Legacy schema is not version 1")
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise MemoryError("INTEGRITY_ERROR", "Legacy database is corrupted")
            if db.execute("PRAGMA foreign_key_check").fetchone():
                raise MemoryError("INTEGRITY_ERROR", "Legacy foreign keys are invalid")
            if db.execute("SELECT 1 FROM operations WHERE state!='DONE' LIMIT 1").fetchone():
                raise MemoryError(
                    "RECOVERY_CONFLICT",
                    "Recover pending operations using the old version before migration",
                )
            known_topics = {row[0] for row in db.execute("SELECT id FROM topics")}
            with closing(sqlite3.connect(db_out)) as target:
                db.backup(target)
        for relative, expected in inventory:
            legacy = source / relative
            new_rel = "L3/" + relative[3:] if relative.startswith("L1/") else relative
            new = stage / new_rel
            new.parent.mkdir(parents=True, exist_ok=True)
            if relative.startswith("L1/") and relative.endswith(".md"):
                new.write_bytes(
                    _convert_old_document(legacy.read_bytes(), relative, known_topics)
                )
            else:
                shutil.copyfile(legacy, new)
            if _hash(legacy) != expected:
                raise MemoryError(
                    "CONFLICT", "Legacy file changed while migrating", {"path": relative}
                )

        from .backup import create_snapshot
        from .health import get_health
        from .index import rebuild_index
        from .store import open_store

        with open_store(stage) as migrated:
            rebuild_index(migrated)
            health = get_health(migrated, deep=True)
            if not health.ready:
                raise MemoryError(
                    "INTEGRITY_ERROR", "Migrated store did not verify", {"issues": health.issues}
                )
            create_snapshot(migrated)

        if any(_hash(source / rel) != expected for rel, expected in inventory):
            raise MemoryError("CONFLICT", "Legacy sources changed during migration")
        if destination.exists():
            raise MemoryError("CONFLICT", "Destination appeared during migration")
        os.rename(stage, destination)
        fsync_directory(destination.parent)
        stage = None
        return {
            "destination": str(destination),
            "source_unchanged": True,
            "documents": len([p for p, _ in inventory if p.startswith(("L1/", "L2/")) and p.endswith(".md")]),
            "status": "verified",
        }
    finally:
        if stage is not None:
            shutil.rmtree(stage)
        lock.release()
