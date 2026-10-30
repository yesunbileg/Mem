import pytest
from mem.documents import load_documents
from mem.read import read_memory
from mem.errors import MemoryError
from .helpers import seed_document,DOC,TOPIC

def test_rename_keeps_document_ref(store):
    data=seed_document(store)
    p=store.root/'L1/devices.md'
    p.rename(store.root/'L1/машин.md')
    r=read_memory(store,f'mem://document/{DOC}')
    assert r.data['path']=='L1/машин.md'
    assert 'Өгөгдөл' in r.data['markdown']
    import hashlib
    assert r.source_etag==hashlib.sha256(data).hexdigest()

def test_duplicate_document_id_fails(store):
    data=seed_document(store)
    (store.root/'L1/copy.md').write_bytes(data)
    with pytest.raises(MemoryError,match='INDEX_INVALID'): load_documents(store)

@pytest.mark.parametrize('replacement',[b'---\nx: 1\nx: 2\n---\nbad',b'\xff',b'x'*(1024*1024+1)])
def test_invalid_document_fails(store,replacement):
    (store.root/'L1/bad.md').write_bytes(replacement)
    with pytest.raises(MemoryError): load_documents(store)

def test_unknown_topic_fails(store):
    data=seed_document(store).replace(TOPIC.encode(),b'55555555-5555-4555-8555-555555555555')
    (store.root/'L1/devices.md').write_bytes(data)
    with pytest.raises(MemoryError,match='INDEX_INVALID'): load_documents(store)
