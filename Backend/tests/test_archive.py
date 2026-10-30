import hashlib,json,zipfile,subprocess,sys
import pytest
from mem.apply import apply_patch
from mem.models import MemoryPatch
from mem.errors import MemoryError
from mem.inbox import list_inbox,read_inbox
from .helpers import count_events

def inbox_patch(store,key='archive',body='Энгийн асуулт\r\n'):
    raw=body.encode();path=store.root/'L0/Inbox/chat-001.md';path.write_bytes(raw)
    return MemoryPatch(idempotency_key=key,close_inbox=[dict(relative_path='L0/Inbox/chat-001.md',expected_sha256=hashlib.sha256(raw).hexdigest(),archive_filename='Mem-MCP-холболт.md',outcome='no_memory',reason='No durable facts')]),raw

def test_archive_uses_topic_filename_and_preserves_source_bytes(store):
    patch,raw=inbox_patch(store)
    assert list_inbox(store,None).items[0]['sha256']==hashlib.sha256(raw).hexdigest()
    assert read_inbox(store,patch.close_inbox[0].relative_path,patch.close_inbox[0].expected_sha256).raw_bytes==raw
    first=apply_patch(store,patch);again=apply_patch(store,patch)
    assert first.state==again.state=='DONE'
    assert count_events(store)==0
    zips=list((store.root/'L0/Archive').rglob('*.zip'))
    assert len(zips)==1 and zips[0].name=='Mem-MCP-холболт.zip'
    with zipfile.ZipFile(zips[0]) as z:
        assert z.read('Mem-MCP-холболт.md')==raw
        m=json.loads(z.read('manifest.json'));assert m['original_filename']=='chat-001.md'
    assert not (store.root/'L0/Inbox/chat-001.md').exists()
    assert store.db.execute('SELECT length(raw) FROM operation_sources').fetchone()[0]==0

@pytest.mark.parametrize('filename',['../out.md','/tmp/x.md','bad\\name.md','CON.md','bad.txt'])
def test_unsafe_archive_filename_rejected(store,filename):
    p,_=inbox_patch(store);p.close_inbox[0].archive_filename=filename
    with pytest.raises(MemoryError):apply_patch(store,p)
    assert (store.root/'L0/Inbox/chat-001.md').exists()
    assert store.db.execute('SELECT count(*) FROM operations').fetchone()[0]==0

def test_duplicate_source_stays_in_inbox(store):
    p,raw=inbox_patch(store);apply_patch(store,p)
    p,_=inbox_patch(store,key='duplicate')
    with pytest.raises(MemoryError,match='SOURCE_ALREADY_PROCESSED'):apply_patch(store,p)
    assert (store.root/'L0/Inbox/chat-001.md').read_bytes()==raw

def test_archive_error_retains_raw_and_retry_finishes(store,monkeypatch):
    import mem.archive as archive
    p,raw=inbox_patch(store)
    original=archive.publish_archive
    def fail(*a,**k):raise OSError('disk full')
    monkeypatch.setattr(archive,'publish_archive',fail)
    r=apply_patch(store,p)
    assert r.state=='APPLIED' and r.archive_status=='pending'
    assert (store.root/'L0/Inbox/chat-001.md').read_bytes()==raw
    monkeypatch.setattr(archive,'publish_archive',original)
    assert apply_patch(store,p).state=='DONE'

def test_changed_input_keeps_new_bytes(store):
    from mem.journal import prepare_operation
    from mem.recovery import recover_pending
    p,raw=inbox_patch(store);prepare_operation(store,p)
    (store.root/'L0/Inbox/chat-001.md').write_bytes(b'new input')
    assert not recover_pending(store).conflicts
    assert (store.root/'L0/Inbox/chat-001.md').read_bytes()==b'new input'
    with zipfile.ZipFile(next((store.root/'L0/Archive').rglob('*.zip'))) as z:assert z.read('Mem-MCP-холболт.md')==raw

def test_oversized_input_and_recorded_without_changes_rejected(store):
    p,_=inbox_patch(store);p.close_inbox[0].outcome='recorded'
    with pytest.raises(MemoryError):apply_patch(store,p)
    (store.root/'L0/Inbox/big.md').write_bytes(b'x'*(10*1024*1024+1))
    with pytest.raises(MemoryError):read_inbox(store,'L0/Inbox/big.md','x')

def test_crash_after_zip_before_unlink(tmp_path):
    from mem.store import init_store,open_store
    root=tmp_path/'m'
    with init_store(root) as s:p,raw=inbox_patch(s)
    code='''
import sys,os
from mem.store import open_store
from mem.models import MemoryPatch
from mem.apply import apply_patch
import mem.archive as a
original=a.publish_archive
def die(*args,**kwargs):
    original(*args,**kwargs)
    os._exit(72)
a.publish_archive=die
s=open_store(sys.argv[1]);apply_patch(s,MemoryPatch.model_validate_json(sys.stdin.read()))
'''
    r=subprocess.run([sys.executable,'-c',code,str(root)],input=p.model_dump_json(),text=True,capture_output=True)
    assert r.returncode==72,r.stderr
    with open_store(root) as s:
        assert apply_patch(s,p).state=='DONE'
        assert len(list((root/'L0/Archive').rglob('*.zip')))==1
        assert count_events(s)==0
