import pytest

from mem.errors import MemoryError
from mem.paths import resolve_safe_path


@pytest.mark.parametrize(
    "path", ["../outside", "/tmp/out", "L1/../../out", "L1/x\\evil"]
)
def test_escape_paths_rejected(store, path):
    with pytest.raises(MemoryError):
        resolve_safe_path(store.root, path, "L1")


def test_escaping_symlink_rejected(store, tmp_path):
    (store.root / "L1/link").symlink_to(tmp_path)
    with pytest.raises(MemoryError):
        resolve_safe_path(store.root, "L1/link/out.md", "L1")
