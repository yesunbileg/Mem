from . import journal
from .errors import MemoryError
from .models import ApplyResult
from .recovery import finish_operation


def apply_patch(store, patch):
    with store.mutex:
        previous = store.db.execute(
            "SELECT * FROM operations WHERE key=?", (patch.idempotency_key,)
        ).fetchone()
        if previous and previous["fingerprint"] != journal.request_fingerprint(patch):
            raise MemoryError(
                "IDEMPOTENCY_CONFLICT", "Key already used for another request"
            )
        store.ensure_ready()
        if store.schema_version != 2 and not previous:
            raise MemoryError("SCHEMA_UNSUPPORTED", "Existing v1 history requires explicit migration")
        if not previous:
            prepared = journal.prepare_operation(store, patch)
            previous = store.db.execute(
                "SELECT * FROM operations WHERE id=?", (prepared.operation_id,)
            ).fetchone()
            finish_operation(store, previous)
        return ApplyResult.model_validate_json(
            store.db.execute(
                "SELECT result FROM operations WHERE key=?", (patch.idempotency_key,)
            ).fetchone()[0]
        )
