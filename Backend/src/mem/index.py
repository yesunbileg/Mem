import json
import os
import sqlite3
import tempfile
import unicodedata
from contextlib import closing

from .documents import digest, load_documents
from .events import event_data, read_event_chain
from .models import IndexReport
from .paths import resolve_safe_path
from .recovery import fsync_directory
from .shorthand import expand_for_index, get_shorthand


def source_revision(store):
    return int(
        store.db.execute(
            "SELECT value FROM metadata WHERE key='source_revision'"
        ).fetchone()[0]
    )


def source_stamp(store, docs):
    return json.dumps(
        dict(
            revision=source_revision(store), documents={d.path: d.sha256 for d in docs}
        ),
        sort_keys=True,
    )


def _path(store):
    return resolve_safe_path(
        store.root, "Backend/.state/search.sqlite3", "Backend/.state"
    )


def _build(store, docs):
    path = _path(store)
    fd, temp = tempfile.mkstemp(dir=path.parent, suffix=".sqlite3")
    os.close(fd)
    db = None
    try:
        db = sqlite3.connect(temp)
        db.executescript(
            "CREATE TABLE metadata(stamp TEXT); CREATE TABLE records(ref TEXT PRIMARY KEY,layer TEXT,topics TEXT, data TEXT); CREATE VIRTUAL TABLE fts USING fts5(ref UNINDEXED,title,body,tokenize='unicode61 remove_diacritics 0');"
        )

        def add(ref, layer, topics, title, body, data):
            db.execute(
                "INSERT INTO records VALUES (?,?,?,?)",
                (ref, layer, json.dumps(topics), json.dumps(data, ensure_ascii=False)),
            )
            db.execute(
                "INSERT INTO fts VALUES (?,?,?)",
                (
                    ref,
                    unicodedata.normalize("NFC", title),
                    unicodedata.normalize("NFC", body),
                ),
            )

        for d in docs:
            add(
                "mem://document/" + d.document_id,
                d.layer,
                d.topic_ids,
                d.title,
                d.markdown,
                dict(source_etag=d.sha256, record_status="active"),
            )
        meanings = get_shorthand(store)
        events = store.db.execute("SELECT id FROM events ORDER BY rowid").fetchall()
        for row in events:
            e = event_data(store, row[0])
            chain = read_event_chain(store, row[0])
            latest = chain.effective_event
            corrected = latest["id"] != e["id"]
            add(
                "mem://event/" + e["id"],
                "L1",
                e["topic_ids"],
                e["summary"],
                expand_for_index(e["summary"] + "\n" + e["details"], meanings),
                dict(
                    source_etag=digest(json.dumps(e, sort_keys=True).encode()),
                    record_status="corrected"
                    if corrected
                    else ("correction" if e["corrects_event_id"] else "active"),
                    latest_correction_ref="mem://event/" + latest["id"]
                    if corrected
                    else None,
                    effective_summary=latest["summary"],
                    evidence_kind=e["evidence_kind"],
                ),
            )
        db.execute("INSERT INTO metadata VALUES (?)", (source_stamp(store, docs),))
        db.commit()
        db.close()
        db = None
        with open(temp, "rb") as f:
            os.fsync(f.fileno())
        os.replace(temp, path)
        fsync_directory(path.parent)
        return IndexReport(
            documents=len(docs),
            events=len(events),
            source_revision=source_revision(store),
        )
    finally:
        if db:
            db.close()
        if os.path.exists(temp):
            os.unlink(temp)


def rebuild_index(store):
    with store.mutex:
        store.ensure_ready()
        docs, issues = load_documents(
            store, tolerate_invalid=True, include_issues=True
        )
        report = _build(store, docs)
        report.invalid_sources = [i["path"] for i in issues]
        return report


def ensure_index_current(store):
    with store.mutex:
        store.ensure_ready()
        docs, issues = load_documents(
            store, tolerate_invalid=True, include_issues=True
        )
        invalid_paths = [i["path"] for i in issues]
        path = _path(store)
        stamp = None
        try:
            if path.exists():
                with closing(sqlite3.connect(path)) as db:
                    stamp = db.execute("SELECT stamp FROM metadata").fetchone()[0]
        except (sqlite3.DatabaseError, TypeError):
            pass
        if stamp != source_stamp(store, docs):
            report = _build(store, docs)
            report.invalid_sources = invalid_paths
            return report
        return IndexReport(
            documents=len(docs),
            events=store.db.execute("SELECT count(*) FROM events").fetchone()[0],
            source_revision=source_revision(store),
            invalid_sources=invalid_paths,
        )
