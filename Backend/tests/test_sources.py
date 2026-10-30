import hashlib
import pytest
from mem.models import SourceDraft
from mem.sources import capture_source
from mem.errors import MemoryError

def test_source_excerpt_and_hash():
    s=capture_source(SourceDraft(ref='new:s',kind='session',origin_ref='s:1',excerpt='Өгөгдөл'),None)
    assert s.excerpt=='Өгөгдөл'
    assert s.sha256==hashlib.sha256('Өгөгдөл'.encode()).hexdigest()

@pytest.mark.parametrize('text',['password=super-secret-value','api_key=abcdefghijk123456789'])
def test_credentials_rejected(text):
    with pytest.raises(MemoryError):capture_source(SourceDraft(ref='new:s',kind='session',origin_ref='s',excerpt=text),None)
