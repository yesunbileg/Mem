import sqlite3
import threading
from importlib.resources import files
from pathlib import Path

from .errors import MemoryError
from .locking import acquire_lock


class Store:
    def __init__(self, root, db, lock):
        self.root, self.db, self.lock = root, db, lock
        self.db_path = root / "L1/history.sqlite3"
        self.index_path = root / "Backend/.state/search.sqlite3"
        self.mutex = threading.RLock()
        self.schema_version = db.execute("PRAGMA user_version").fetchone()[0]
        self.schema_version = db.execute("PRAGMA user_version").fetchone()[0]

    def close(self):
        self.db.close()
        self.lock.release()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def ensure_ready(self):
        if self.db.execute(
            "SELECT 1 FROM operations WHERE state!='DONE' LIMIT 1"
        ).fetchone():
            from .recovery import recover_pending

            report = recover_pending(self)
            if report.conflicts:
                raise MemoryError(
                    "RECOVERY_CONFLICT",
                    "Resolve pending operation",
                    {"operations": report.conflicts},
                )


def _connect(root, create):
    root = Path(root).resolve()
    dbpath = root / "L1/history.sqlite3"
    legacy_db = root / "L3/history.sqlite3"
    legacy_snapshot = root / "L3/history.snapshot.sqlite3"
    legacy_markdown = (root / "L1").exists() and any((root / "L1").rglob("*.md"))
    if legacy_db.exists() or legacy_snapshot.exists() or legacy_markdown:
        raise MemoryError(
            "SCHEMA_UNSUPPORTED",
            "Legacy L1 Markdown / L3 SQLite layout detected; run mem migrate-layers",
            {"source": str(root)},
        )
    if create and not dbpath.exists() and (root / "L1/history.snapshot.sqlite3").exists():
        raise MemoryError("SCHEMA_UNSUPPORTED", "Existing snapshot requires explicit restore or migration")
    if create and not dbpath.exists() and (root / "L1/history.snapshot.sqlite3").exists():
        raise MemoryError("SCHEMA_UNSUPPORTED", "Snapshot requires explicit restore")
    if not create and not dbpath.is_file():
        raise MemoryError("NOT_FOUND", "Store not initialized")
    if not create and dbpath.stat().st_size == 0:
        raise MemoryError("SCHEMA_UNSUPPORTED")
    for rel in ["Backend/.state", "L1", "L3", "L2", "L0/Inbox", "L0/Archive"]:
        p = root / rel
        if not p.resolve().is_relative_to(root):
            raise MemoryError("VALIDATION_ERROR", "Store path escapes root")
        p.mkdir(parents=True, exist_ok=True)
    if dbpath.is_symlink() or (root / "Backend/.state/store.lock").is_symlink():
        raise MemoryError("VALIDATION_ERROR", "Symlink at store control path")
    lock = acquire_lock(root / "Backend/.state/store.lock")
    db = None
    try:
        db = sqlite3.connect(dbpath, check_same_thread=False)
        db.row_factory = sqlite3.Row
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version not in ([0, 1, 2] if create else [1, 2]):
            raise MemoryError("SCHEMA_UNSUPPORTED")
        if version == 0:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                raise MemoryError("SCHEMA_UNSUPPORTED")
            sql = files("mem").joinpath("migrations/002_initial.sql").read_text()
            db.executescript("BEGIN;\n" + sql + "\nCOMMIT;")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("CREATE VIRTUAL TABLE temp.fts_probe USING fts5(text)")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise MemoryError("INTEGRITY_ERROR")
        return Store(root, db, lock)
    except Exception:
        if db:
            db.close()
        lock.release()
        raise


def init_store(root: Path) -> Store:
    return _connect(root, True)


def open_store(root: Path) -> Store:
    return _connect(root, False)
