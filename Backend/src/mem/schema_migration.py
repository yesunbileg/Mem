"""Explicit, non-destructive migration of a schema-v1 SQLite history copy to v2.

The existing live DB and snapshot are never modified. The caller controls when
to adopt the verified new copy. Older source excerpts are not invented as
complete transcripts.
"""

import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from .errors import MemoryError
from .recovery import fsync_directory


def migrate_v1_database(source, destination):
    source = Path(source).absolute()
    destination = Path(destination).absolute()
    if (
        not source.is_file()
        or source.is_symlink()
        or destination.is_symlink()
        or destination.exists()
        or source == destination
    ):
        raise MemoryError(
            "CONFLICT", "Source must be a regular v1 DB and destination must not exist"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".mem-v2-", suffix=".sqlite3", dir=destination.parent)
    os.close(fd)
    try:
        try:
            with closing(
                sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
            ) as old:
                if old.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise MemoryError("SCHEMA_UNSUPPORTED", "Source is not schema v1")
                if old.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise MemoryError("INTEGRITY_ERROR", "Damaged v1 database")
                if old.execute("PRAGMA foreign_key_check").fetchone():
                    raise MemoryError("INTEGRITY_ERROR", "Invalid v1 references")
                if old.execute(
                    "SELECT 1 FROM operations WHERE state!='DONE' LIMIT 1"
                ).fetchone():
                    raise MemoryError("RECOVERY_CONFLICT", "Resolve pending v1 operations first")
                with closing(sqlite3.connect(temp)) as copy:
                    old.backup(copy)
            with closing(sqlite3.connect(temp)) as copy:
                copy.execute("BEGIN IMMEDIATE")
                copy.execute(
                    "ALTER TABLE sources ADD COLUMN full_text TEXT NOT NULL DEFAULT ''"
                )
                copy.execute(
                    "UPDATE sources SET full_text=excerpt WHERE kind!='inbox'"
                )
                copy.execute("ALTER TABLE events ADD COLUMN speaker TEXT")
                copy.execute("PRAGMA user_version=2")
                copy.commit()
                if copy.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise MemoryError("INTEGRITY_ERROR", "Migrated database invalid")
                if copy.execute("PRAGMA foreign_key_check").fetchone():
                    raise MemoryError("INTEGRITY_ERROR", "Migrated references invalid")
            with open(temp, "rb") as stream:
                os.fsync(stream.fileno())
            os.link(temp, destination)
            fsync_directory(destination.parent)
            return {
                "status": "verified",
                "source_unchanged": True,
                "destination": str(destination),
                "schema_version": 2,
                "historical_source_note": (
                    "Existing excerpts preserved; unavailable original "
                    "raw transcripts were not fabricated"
                ),
            }
        except sqlite3.DatabaseError as exc:
            raise MemoryError("INTEGRITY_ERROR", "Invalid schema-v1 database") from exc
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
