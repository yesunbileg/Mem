import json
import subprocess
import sys
import pytest
from mem.store import init_store,open_store
from mem.read import read_memory
from mem.errors import MemoryError
from .helpers import sample_patch,count_events

@pytest.mark.parametrize('point',['prepare_operation','install_file','commit_operation'])
def test_process_crash_recovers_once(tmp_path,point):
    root=tmp_path/'memory';init_store(root).close()
    code='''
import sys,json,os
from mem.store import open_store
from mem.models import MemoryPatch
from mem.apply import apply_patch
import mem.journal as journal
import mem.recovery as recovery
mod = journal if sys.argv[2]=='prepare_operation' else recovery
fn = getattr(mod,sys.argv[2])
def terminate(*args,**kwargs):
    result=fn(*args,**kwargs)
    os._exit(71)
setattr(mod,sys.argv[2],terminate)
s=open_store(sys.argv[1]);apply_patch(s,MemoryPatch.model_validate_json(sys.stdin.read()))
'''
    p=sample_patch()
    result=subprocess.run([sys.executable,'-c',code,str(root),point],input=p.model_dump_json(),text=True,capture_output=True)
    assert result.returncode==71,result.stderr
    with open_store(root) as s:
        from mem.apply import apply_patch
        a=apply_patch(s,p)
        assert a.state=='DONE'
        assert count_events(s)==1
        assert read_memory(s,'mem://document/'+a.id_map['new:d']).data['title']=='Mem project'
        assert apply_patch(s,p).id_map==a.id_map

def test_recovery_conflict_preserves_external_bytes(store):
    from mem.journal import prepare_operation
    from mem.recovery import recover_pending
    prepare_operation(store,sample_patch())
    path=store.root/'L1/projects.md';path.write_bytes(b'external file')
    report=recover_pending(store)
    assert len(report.conflicts)==1
    assert path.read_bytes()==b'external file'
    assert count_events(store)==0
    with pytest.raises(MemoryError,match='RECOVERY_CONFLICT'):read_memory(store,'mem://topic/11111111-1111-4111-8111-111111111111')
