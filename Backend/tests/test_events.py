from mem.events import read_event_chain
from .helpers import TOPIC,EVENT,CORRECTION

def test_read_event_includes_corrections(store):
    for ident,kind,summary,target in [(EVENT,'test','Тест PASS',None),(CORRECTION,'correction','Тест FAIL — өмнөх дүн буруу',EVENT)]:
        store.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',(ident,kind,summary,'',None,'2026-10-30T00:00:00Z','tool_observed',target,None))
    store.db.commit()
    chain=read_event_chain(store,EVENT)
    assert chain.original['summary']=='Тест PASS'
    assert chain.effective_event['summary']=='Тест FAIL — өмнөх дүн буруу'
    assert chain.original['occurred_at'] is None
    assert len(chain.corrections)==1
