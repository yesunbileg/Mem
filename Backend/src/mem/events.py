from dataclasses import dataclass
from uuid import UUID
from .errors import MemoryError

@dataclass
class EventChain:
    original: dict
    corrections: list[dict]
    effective_event: dict

def event_data(store,event_id):
    row=store.db.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
    if not row:raise MemoryError('NOT_FOUND','Event not found')
    data=dict(row)
    data['topic_ids']=[r[0] for r in store.db.execute('SELECT topic_id FROM event_topics WHERE event_id=? ORDER BY topic_id',(event_id,))]
    data['source_refs']=['mem://source/'+r[0] for r in store.db.execute('SELECT source_id FROM event_sources WHERE event_id=? ORDER BY source_id',(event_id,))]
    return data

def read_event_chain(store,event_id):
    item=event_data(store,str(event_id));seen=set()
    while item['corrects_event_id']:
        if item['id'] in seen:raise MemoryError('INTEGRITY_ERROR','Correction cycle')
        seen.add(item['id']);item=event_data(store,item['corrects_event_id'])
    original=item;corrections=[];seen=set()
    while True:
        if item['id'] in seen:raise MemoryError('INTEGRITY_ERROR','Correction cycle')
        seen.add(item['id'])
        row=store.db.execute('SELECT id FROM events WHERE corrects_event_id=?',(item['id'],)).fetchone()
        if not row:break
        item=event_data(store,row[0]);corrections.append(item)
    return EventChain(original,corrections,item)
