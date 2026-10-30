import pytest

from mem.store import init_store


@pytest.fixture
def store(tmp_path):
    s = init_store(tmp_path / "memory")
    yield s
    s.close()
