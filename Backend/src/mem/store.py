from pathlib import Path
import sqlite3
import threading
from importlib.resources import files
from .locking import acquire_lock
from .errors import MemoryError

class Store:
    def __init__(self,root,db,lock):
        self.root, self.db, self.lock = root, db, lock
        self.db_path = root/'L3/history.sqlite3'
        self.index_path = root/'Backend/.state/search.sqlite3'
        self.mutex = threading.RLock()
    def close(self):
        self.db.close()
        self.lock.release()
    def __enter__(self): return self
    def __exit__(self,*args): self.close()
    def ensure_ready(self):
        if self.db.execute("SELECT 1 FROM operations WHERE state!='DONE' LIMIT 1").fetchone():
            from .recovery import recover_pending
            report = recover_pending(self)
            if report.conflicts: raise MemoryError('RECOVERY_CONFLICT','Resolve pending operation',{'operations':report.conflicts})


def _connect(root,create):
    root=Path(root).resolve()
    dbpath=root/'L3/history.sqlite3'
    if not create and not dbpath.is_file(): raise MemoryError('NOT_FOUND','Store not initialized')
    if not create and dbpath.stat().st_size == 0: raise MemoryError('SCHEMA_UNSUPPORTED')
    for rel in ['Backend/.state','L3','L1','L2','L0/Inbox','L0/Archive']:
        p=root/rel
        if not p.resolve().is_relative_to(root): raise MemoryError('VALIDATION_ERROR','Store path escapes root')
        p.mkdir(parents=True,exist_ok=True)
    if dbpath.is_symlink() or (root/'Backend/.state/store.lock').is_symlink(): raise MemoryError('VALIDATION_ERROR','Symlink at store control path')
    lock=acquire_lock(root/'Backend/.state/store.lock')
    db=None
    try:
        db=sqlite3.connect(dbpath,check_same_thread=False)
        db.row_factory=sqlite3.Row
        version=db.execute('PRAGMA user_version').fetchone()[0]
        if version not in ([0,1] if create else [1]): raise MemoryError('SCHEMA_UNSUPPORTED')
        if version == 0:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone(): raise MemoryError('SCHEMA_UNSUPPORTED')
            sql=files('mem').joinpath('migrations/001_initial.sql').read_text()
            db.executescript('BEGIN;\n'+sql+'\nCOMMIT;')
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA busy_timeout=5000')
        db.execute('CREATE VIRTUAL TABLE temp.fts_probe USING fts5(text)')
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok': raise MemoryError('INTEGRITY_ERROR')
        return Store(root,db,lock)
    except Exception:
        if db: db.close()
        lock.release()
        raise

def init_store(root: Path) -> Store: return _connect(root,True)
def open_store(root: Path) -> Store: return _connect(root,False)
