from dataclasses import asdict
import json
from uuid import UUID
from .models import ReadResult
from .documents import load_documents,digest
from .events import read_event_chain
from .errors import MemoryError

def split_ref(ref):
    try:
        prefix,kind,ident=ref.split('/')[-3:]
        if not ref.startswith('mem://') or kind not in ('topic','document','event','source'):raise ValueError()
        return kind,str(UUID(ident))
    except (ValueError,AttributeError):raise MemoryError('VALIDATION_ERROR','Invalid memory ref') from None

def read_memory(store,ref):
    with store.mutex:
        store.ensure_ready()
        kind,ident=split_ref(ref)
        if kind=='document':
            doc=next((d for d in load_documents(store) if d.document_id==ident),None)
            if not doc:raise MemoryError('NOT_FOUND','Document not found')
            return ReadResult(ref=ref,kind=kind,data=doc.public(),source_etag=doc.sha256)
        if kind=='event':data=asdict(read_event_chain(store,ident))
        elif kind=='topic':
            row=store.db.execute('SELECT * FROM topics WHERE id=?',(ident,)).fetchone()
            if not row:raise MemoryError('NOT_FOUND','Topic not found')
            data=dict(row)
            data['document_refs']=['mem://document/'+d.document_id for d in load_documents(store) if ident in d.topic_ids]
            data['event_refs']=['mem://event/'+r[0] for r in store.db.execute('SELECT event_id FROM event_topics WHERE topic_id=?',(ident,))]
        else:
            row=store.db.execute('SELECT * FROM sources WHERE id=?',(ident,)).fetchone()
            if not row:raise MemoryError('NOT_FOUND','Source not found')
            data=dict(row)
            if data['archive_ref']:
                from .archive import read_archived_source
                data['text']=read_archived_source(store,data['archive_ref']).decode('utf-8')
        return ReadResult(ref=ref,kind=kind,data=data,source_etag=digest(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()))
