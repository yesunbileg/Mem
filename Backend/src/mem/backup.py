"""Explicit consistent SQLite snapshots and complete portable store backups."""

import json
import os
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from .documents import digest, now
from .errors import MemoryError
from .health import get_health
from .index import rebuild_index, source_revision
from .paths import resolve_safe_path
from .recovery import fsync_directory
from .store import open_store

MAX_BACKUP_BYTES = 1024 * 1024 * 1024


@dataclass
class BackupManifest:
    schema_version: int
    source_revision: int
    created_at: str
    files: dict[str, str]


def _ready(store):
    store.ensure_ready()
    if (
        not get_health(store, deep=True).ready
        or store.db.execute("SELECT 1 FROM operations WHERE state!='DONE'").fetchone()
    ):
        raise MemoryError("RECOVERY_CONFLICT", "Resolve store before snapshot/backup")


def _sqlite_copy(source_db, destination):
    with closing(sqlite3.connect(destination)) as target:
        source_db.backup(target)
        if (
            target.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or target.execute("PRAGMA foreign_key_check").fetchone()
        ):
            raise MemoryError("INTEGRITY_ERROR")
        target.commit()
    with open(destination, "rb") as f:
        os.fsync(f.fileno())


def create_snapshot(store):
    with store.mutex:
        _ready(store)
        destination = resolve_safe_path(store.root, "L3/history.snapshot.sqlite3", "L3")
        fd, temp = tempfile.mkstemp(dir=destination.parent, suffix=".sqlite3")
        os.close(fd)
        try:
            _sqlite_copy(store.db, temp)
            os.replace(temp, destination)
            fsync_directory(destination.parent)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return destination


def restore_snapshot(snapshot_path, destination):
    snapshot_path = Path(snapshot_path).resolve()
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise MemoryError("CONFLICT", "Destination must not exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=destination.parent, suffix=".sqlite3")
    os.close(fd)
    try:
        with closing(
            sqlite3.connect(snapshot_path.as_uri() + "?mode=ro", uri=True)
        ) as source:
            if source.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise MemoryError("SCHEMA_UNSUPPORTED")
            if source.execute(
                "SELECT 1 FROM operations WHERE state!='DONE'"
            ).fetchone():
                raise MemoryError("RECOVERY_CONFLICT")
            _sqlite_copy(source, temp)
        os.link(temp, destination)
        fsync_directory(destination.parent)
    except sqlite3.DatabaseError:
        raise MemoryError("INTEGRITY_ERROR", "Invalid SQLite snapshot") from None
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _inventory(store):
    result = {}
    for area in ["L1", "L2", "L0/Inbox", "L0/Archive"]:
        for path in sorted((store.root / area).rglob("*")):
            rel = path.relative_to(store.root).as_posix()
            path = resolve_safe_path(store.root, rel, area)
            if path.is_file() and not path.name.startswith(".mem-"):
                result[rel] = digest(path.read_bytes())
    return result


def create_backup(store, destination):
    with store.mutex:
        _ready(store)
        destination = Path(destination).resolve()
        if destination.is_relative_to(store.root):
            raise MemoryError(
                "VALIDATION_ERROR", "Backup output must be outside store root"
            )
        if destination.exists():
            raise MemoryError("CONFLICT", "Backup already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=destination.parent, prefix=".mem-backup-"
        ) as stage:
            stage = Path(stage)
            dbfile = stage / "history.sqlite3"
            _sqlite_copy(store.db, dbfile)
            inventory = _inventory(store)
            hashes = {"L3/history.sqlite3": digest(dbfile.read_bytes()), **inventory}
            manifest = BackupManifest(1, source_revision(store), now(), hashes)
            output = stage / "backup.zip"
            total = 0
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.write(dbfile, "L3/history.sqlite3")
                for rel, sha in inventory.items():
                    raw = (store.root / rel).read_bytes()
                    total += len(raw)
                    if total > MAX_BACKUP_BYTES:
                        raise MemoryError(
                            "VALIDATION_ERROR", "Backup exceeds 1 GiB v0.1 limit"
                        )
                    if digest(raw) != sha:
                        raise MemoryError("CONFLICT", "Source changed during backup")
                    z.writestr(rel, raw)
                z.writestr(
                    "manifest.json",
                    json.dumps(asdict(manifest), ensure_ascii=False, sort_keys=True),
                )
            if _inventory(store) != inventory:
                raise MemoryError("CONFLICT", "Source inventory changed during backup")
            with zipfile.ZipFile(output) as z:
                if z.testzip():
                    raise MemoryError("INTEGRITY_ERROR")
            with open(output, "rb") as f:
                os.fsync(f.fileno())
            os.link(output, destination)
            fsync_directory(destination.parent)
        return manifest


def _validate_member(name):
    parts = PurePosixPath(name).parts
    if (
        not parts
        or PurePosixPath(name).is_absolute()
        or ".." in parts
        or "\\" in name
        or ":" in name
        or name.endswith("/")
        or str(PurePosixPath(name)) != name
    ):
        raise MemoryError("VALIDATION_ERROR", "Unsafe backup member")
    allowed = name == "L3/history.sqlite3" or any(
        name.startswith(p) for p in ["L1/", "L2/", "L0/Inbox/", "L0/Archive/"]
    )
    if not allowed:
        raise MemoryError("VALIDATION_ERROR", "Unsupported backup member")


def restore_backup(backup_path, destination):
    destination = Path(destination).absolute()
    if destination.is_symlink() or (
        destination.exists()
        and (not destination.is_dir() or any(destination.iterdir()))
    ):
        raise MemoryError("CONFLICT", "Restore destination must be new or empty")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            zipfile.ZipFile(backup_path) as z,
            tempfile.TemporaryDirectory(
                dir=destination.parent, prefix=".mem-restore-"
            ) as temp,
        ):
            stage = Path(temp) / "store"
            stage.mkdir()
            infos = z.infolist()
            if (
                len(infos) > 100000
                or sum(i.file_size for i in infos) > MAX_BACKUP_BYTES + 10 * 1024 * 1024
            ):
                raise MemoryError(
                    "VALIDATION_ERROR", "Backup exceeds v0.1 restore limits"
                )
            if len(z.namelist()) != len(set(z.namelist())):
                raise MemoryError("VALIDATION_ERROR", "Duplicate backup members")
            if z.getinfo("manifest.json").file_size > 10 * 1024 * 1024:
                raise MemoryError("VALIDATION_ERROR", "Manifest too large")
            manifest = json.loads(z.read("manifest.json"))
            if manifest["schema_version"] != 1:
                raise MemoryError("SCHEMA_UNSUPPORTED")
            hashes = manifest["files"]
            if (
                set(z.namelist()) != set(hashes) | {"manifest.json"}
                or "L3/history.sqlite3" not in hashes
            ):
                raise MemoryError("INTEGRITY_ERROR", "Manifest incomplete")
            for name, sha in hashes.items():
                _validate_member(name)
                raw = z.read(name)
                if digest(raw) != sha:
                    raise MemoryError("INTEGRITY_ERROR", "Checksum mismatch")
                p = stage / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)
            with open_store(stage) as restored:
                _ready(restored)
                if source_revision(restored) != manifest["source_revision"]:
                    raise MemoryError("INTEGRITY_ERROR", "Revision mismatch")
                rebuild_index(restored)
                report = get_health(restored, deep=True)
                if not report.ready:
                    raise MemoryError("INTEGRITY_ERROR")
            if destination.exists():
                destination.rmdir()
            os.rename(stage, destination)
            fsync_directory(destination.parent)
            return report
    except (zipfile.BadZipFile, ValueError, KeyError, TypeError, sqlite3.DatabaseError):
        raise MemoryError("INTEGRITY_ERROR", "Invalid backup") from None
