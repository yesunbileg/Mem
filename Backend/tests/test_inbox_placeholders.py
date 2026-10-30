import hashlib

import pytest

from mem.errors import MemoryError
from mem.inbox import list_inbox, read_inbox


def test_empty_directory_marker_is_not_an_inbox_source(store):
    (store.root / "L0/Inbox/.gitkeep").touch()
    (store.root / "L0/Inbox/chat.md").write_text("actual source")
    result = list_inbox(store)
    assert [item["relative_path"] for item in result.items] == ["L0/Inbox/chat.md"]


def test_reserved_directory_marker_cannot_be_processed(store):
    (store.root / "L0/Inbox/.gitkeep").touch()
    with pytest.raises(MemoryError, match="VALIDATION_ERROR"):
        read_inbox(store, "L0/Inbox/.gitkeep", hashlib.sha256(b"").hexdigest())
