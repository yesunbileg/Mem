import sqlite3
from contextlib import closing
from .models import HealthReport
from .documents import load_documents
from .index import source_revision,source_stamp,_path
from .errors import MemoryError

def get_health(store,deep=False):
    with store.mutex:
        issues=[]
        pending=[r[0] for r in store.db.execute("SELECT id FROM operations WHERE state!='DONE'")]
        try:docs=load_documents(store)
        except (MemoryError,OSError) as e:
            docs=[];issues.append(dict(code=getattr(e,'code','IO_ERROR'),severity='error'))
        check='integrity_check' if deep else 'quick_check'
        if store.db.execute('PRAGMA '+check).fetchone()[0]!='ok' or store.db.execute('PRAGMA foreign_key_check').fetchone():issues.append(dict(code='INTEGRITY_ERROR',severity='error'))
        revision=None
        try:
            path=_path(store)
            if path.exists():
                with closing(sqlite3.connect(path)) as db:
                    stamp=db.execute('SELECT stamp FROM metadata').fetchone()[0]
                    import json
                    revision=json.loads(stamp)['revision']
                    if stamp!=source_stamp(store,docs):issues.append(dict(code='INDEX_STALE',severity='warning'))
            else:issues.append(dict(code='INDEX_MISSING',severity='warning'))
        except (sqlite3.DatabaseError,MemoryError,ValueError,TypeError,KeyError):issues.append(dict(code='INDEX_INVALID',severity='warning'))
        if deep:
            from .archive import read_archived_source
            for row in store.db.execute('SELECT DISTINCT archive_ref FROM processed_sources'):
                try:read_archived_source(store,row[0])
                except (MemoryError,OSError):issues.append(dict(code='ARCHIVE_INVALID',severity='error',path=row[0]))
        if pending:issues.append(dict(code='PENDING_OPERATION',severity='warning'))
        for op in store.db.execute("SELECT id FROM operations WHERE state='PREPARED'"):
            issues.append(dict(code='RECOVERY_REQUIRED',severity='error',operation_id=op[0]))
        return HealthReport(ready=not any(i['severity']=='error' for i in issues),issues=issues,source_revision=source_revision(store),index_revision=revision,pending_operations=pending)
