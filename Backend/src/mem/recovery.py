import json
import os
import tempfile
from dataclasses import dataclass, field

from .errors import MemoryError
from .models import ApplyResult
from .paths import resolve_safe_path


@dataclass
class RecoveryReport:
    recovered_operation_ids: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def fsync_directory(path):
    if os.name != "posix":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def current_bytes(path):
    return path.read_bytes() if path.exists() else None


def install_file(store, row):
    path = resolve_safe_path(store.root, row["path"], row["path"].split("/")[0])
    current = current_bytes(path)
    if current == row["after_bytes"]:
        return
    if current != row["before_bytes"]:
        raise MemoryError(
            "RECOVERY_CONFLICT", "External file conflict", {"path": row["path"]}
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if row["after_bytes"] is None:
        path.unlink()
    else:
        fd, name = tempfile.mkstemp(prefix=".mem-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(row["after_bytes"])
                f.flush()
                os.fsync(f.fileno())
            if current_bytes(path) != row["before_bytes"]:
                raise MemoryError("RECOVERY_CONFLICT", "File changed during write")
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    fsync_directory(path.parent)


def commit_operation(store, operation):
    payload = json.loads(operation["payload"])
    opid = operation["id"]
    result = ApplyResult.model_validate_json(operation["result"])
    result.state = "APPLIED"
    with store.db:
        for t in payload["topics"]:
            if t["action"] == "create":
                store.db.execute(
                    "INSERT INTO topics VALUES (?,?,1)", (t["id"], t["title"])
                )
            else:
                store.db.execute(
                    "UPDATE topics SET title=?,revision=revision+1 WHERE id=?",
                    (t["title"], t["id"]),
                )
        if payload.get("shorthand"):
            from .shorthand import get_shorthand

            shorthand = get_shorthand(store)
            for change in payload["shorthand"]:
                if change["action"] == "set":
                    shorthand[change["code"]] = change["expansion"]
                else:
                    shorthand.pop(change["code"], None)
            store.db.execute(
                "INSERT INTO metadata(key,value) VALUES('shorthand',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps(shorthand, ensure_ascii=False, sort_keys=True),),
            )
        for source in payload["sources"]:
            values = (
                source["source_id"], source["kind"], source["origin_ref"],
                source["excerpt"], source["sha256"],
            )
            if store.schema_version == 2:
                store.db.execute(
                    "INSERT INTO sources VALUES (?,?,?,?,?,NULL,?)",
                    (*values, source["full_text"]),
                )
            else:
                store.db.execute("INSERT INTO sources VALUES (?,?,?,?,?,NULL)", values)
        for event in payload["events"]:
            values = (
                event["id"], event["kind"], event["summary"], event["details"],
                event["occurred_at"], event["recorded_at"], event["evidence_kind"],
                event["corrects_event_id"], opid,
            )
            if store.schema_version == 2:
                store.db.execute(
                    "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (*values, event.get("speaker")),
                )
            else:
                store.db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)", values)
                store.db.executemany(
                    "INSERT INTO event_topics VALUES (?,?)",
                    [(event["id"], t) for t in event["topic_ids"]],
                )
            store.db.executemany(
                "INSERT INTO event_sources VALUES (?,?)",
                [(event["id"], source) for source in event["source_ids"]],
            )
        for d in payload["documents"]:
            before = None
            if d["before_path"]:
                row = store.db.execute(
                    "SELECT before_bytes FROM operation_documents WHERE operation_id=? AND path=?",
                    (opid, d["before_path"]),
                ).fetchone()
                before = row[0] if row else None
            store.db.execute(
                "INSERT INTO document_revisions(document_id,before_bytes,operation_id,source_refs) VALUES (?,?,?,?)",
                (d["id"], before, opid, json.dumps(d["source_ids"])),
            )
        store.db.execute(
            "UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='source_revision'"
        )
        store.db.execute(
            "UPDATE operations SET state='APPLIED',result=? WHERE id=?",
            (result.model_dump_json(), opid),
        )


def finish_operation(store, operation):
    opid = operation["id"]
    if operation["state"] == "PREPARED":
        rows = store.db.execute(
            "SELECT * FROM operation_documents WHERE operation_id=? ORDER BY ordinal",
            (opid,),
        ).fetchall()
        for row in rows:
            path = resolve_safe_path(store.root, row["path"], row["path"].split("/")[0])
            if current_bytes(path) not in (row["before_bytes"], row["after_bytes"]):
                raise MemoryError(
                    "RECOVERY_CONFLICT", "External file conflict", {"path": row["path"]}
                )
        for row in rows:
            install_file(store, row)
        commit_operation(store, operation)
    if store.db.execute(
        "SELECT 1 FROM operation_sources WHERE operation_id=?", (opid,)
    ).fetchone():
        from .archive import complete_archives

        archive = complete_archives(store, opid)
        if archive.status != "complete":
            return
    result = ApplyResult.model_validate_json(
        store.db.execute(
            "SELECT result FROM operations WHERE id=?", (opid,)
        ).fetchone()[0]
    )
    result.state = "DONE"
    with store.db:
        store.db.execute(
            "UPDATE operations SET state='DONE',result=? WHERE id=?",
            (result.model_dump_json(), opid),
        )


def recover_pending(store):
    with store.mutex:
        report = RecoveryReport()
        for op in store.db.execute(
            "SELECT * FROM operations WHERE state!='DONE' ORDER BY rowid"
        ).fetchall():
            try:
                finish_operation(store, op)
                report.recovered_operation_ids.append(op["id"])
            except (MemoryError, OSError):
                report.conflicts.append(op["id"])
                break
        return report
