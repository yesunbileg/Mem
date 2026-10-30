from mem.apply import apply_patch
from mem.health import get_health
from mem.journal import prepare_operation

from .helpers import sample_patch
from .test_archive import inbox_patch


def test_cache_problem_not_canonical_data_loss(store):
    assert get_health(store).ready
    assert any(i["code"] == "INDEX_MISSING" for i in get_health(store).issues)
    apply_patch(store, sample_patch())
    (store.root / "L3/invalid.md").write_text("broken")
    assert not get_health(store, deep=True).ready


def test_health_detects_missing_archived_source(store):
    p, _ = inbox_patch(store)
    apply_patch(store, p)
    next((store.root / "L0/Archive").rglob("*.zip")).unlink()
    r = get_health(store, deep=True)
    assert not r.ready
    assert any(i["code"] == "ARCHIVE_INVALID" for i in r.issues)


def test_pending_conflict_is_not_ready(store):
    prepare_operation(store, sample_patch())
    assert not get_health(store).ready
