import json
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .documents import digest
from .errors import MemoryError
from .models import ApplyResult
from .paths import resolve_safe_path
from .recovery import fsync_directory


@dataclass
class ArchiveResult:
    status: str
    archive_refs: list[str] = field(default_factory=list)
    retained_changed_sources: list[str] = field(default_factory=list)


def validate_filename(name, original):
    if (
        not name
        or len(name.encode()) > 220
        or name in (".", "..", "manifest.json")
        or any(c in name for c in '/\\:<>"|?*\x00')
        or any(ord(c) < 32 for c in name)
        or name.endswith((" ", "."))
        or re.match(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", name)
    ):
        raise MemoryError("VALIDATION_ERROR", "Unsafe archive filename")
    if Path(name).suffix.lower() != Path(original).suffix.lower():
        raise MemoryError("VALIDATION_ERROR", "Keep original extension")


def verify_archive(path, source):
    try:
        with zipfile.ZipFile(path) as z:
            if (
                set(z.namelist()) != {source["archive_filename"], "manifest.json"}
                or len(z.namelist()) != 2
            ):
                raise ValueError()
            meta = json.loads(z.read("manifest.json"))
            if (
                meta["source_sha256"] != source["sha256"]
                or meta["source_id"] != source["source_id"]
            ):
                raise ValueError()
            if z.getinfo(source["archive_filename"]).file_size > 10 * 1024 * 1024:
                raise ValueError()
            raw = z.read(source["archive_filename"])
            if z.testzip() or digest(raw) != source["sha256"]:
                raise ValueError()
            return raw
    except (ValueError, KeyError, zipfile.BadZipFile):
        raise MemoryError("ARCHIVE_PENDING", "Archive verification failed") from None


def publish_archive(store, operation_id, source):
    op = store.db.execute(
        "SELECT payload FROM operations WHERE id=?", (operation_id,)
    ).fetchone()
    payload = json.loads(op[0])
    stamp = payload["prepared_at"]
    rel = f"L0/Archive/{stamp[:4]}/{stamp[5:7]}/{operation_id}/{Path(source['archive_filename']).stem}.zip"
    path = resolve_safe_path(store.root, rel, "L0/Archive")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        verify_archive(path, source)
        return rel
    fd, temp = tempfile.mkstemp(prefix=".mem-", suffix=".tmp", dir=path.parent)
    os.close(fd)
    try:
        manifest = dict(
            source_sha256=source["sha256"],
            source_id=source["source_id"],
            operation_id=operation_id,
            original_filename=Path(source["relative_path"]).name,
            original_path=source["relative_path"],
            archive_filename=source["archive_filename"],
            outcome=source["outcome"],
            reason=source["reason"],
            archived_at=stamp,
            memory_refs=list(
                json.loads(
                    store.db.execute(
                        "SELECT result FROM operations WHERE id=?", (operation_id,)
                    ).fetchone()[0]
                )["id_map"].values()
            ),
        )
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(source["archive_filename"], source["raw"])
            z.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            )
        with open(temp, "rb") as f:
            os.fsync(f.fileno())
        verify_archive(temp, source)
        # Hard-link publication is atomic and fails rather than overwriting any final ZIP.
        try:
            os.link(temp, path)
        except FileExistsError:
            verify_archive(path, source)
        fsync_directory(path.parent)
        return rel
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def complete_archives(store, operation_id):
    result = ArchiveResult("complete")
    for row in store.db.execute(
        "SELECT * FROM operation_sources WHERE operation_id=?", (operation_id,)
    ).fetchall():
        source = dict(row)
        try:
            rel = source["archive_ref"] or publish_archive(store, operation_id, source)
            verify_archive(resolve_safe_path(store.root, rel, "L0/Archive"), source)
            original = resolve_safe_path(
                store.root, source["relative_path"], "L0/Inbox"
            )
            if original.exists():
                if digest(original.read_bytes()) == source["sha256"]:
                    original.unlink()
                    fsync_directory(original.parent)
                else:
                    result.retained_changed_sources.append(source["relative_path"])
            with store.db:
                store.db.execute(
                    "UPDATE operation_sources SET archive_ref=?,raw=? WHERE operation_id=? AND source_id=?",
                    (rel, b"", operation_id, source["source_id"]),
                )
                store.db.execute(
                    "UPDATE sources SET archive_ref=? WHERE kind='inbox' AND sha256=?",
                    (rel, source["sha256"]),
                )
                store.db.execute(
                    "INSERT OR IGNORE INTO processed_sources VALUES (?,?)",
                    (source["sha256"], rel),
                )
            result.archive_refs.append(rel)
        except (OSError, MemoryError, zipfile.BadZipFile):
            result.status = "pending"
    output = ApplyResult.model_validate_json(
        store.db.execute(
            "SELECT result FROM operations WHERE id=?", (operation_id,)
        ).fetchone()[0]
    )
    output.archive_status = result.status
    with store.db:
        store.db.execute(
            "UPDATE operations SET result=? WHERE id=?",
            (output.model_dump_json(), operation_id),
        )
    return result


def read_archived_source(store, relative_path):
    row = store.db.execute(
        "SELECT * FROM operation_sources WHERE archive_ref=?", (relative_path,)
    ).fetchone()
    if not row:
        raise MemoryError("NOT_FOUND", "Archive source not found")
    return verify_archive(
        resolve_safe_path(store.root, relative_path, "L0/Archive"), dict(row)
    )
