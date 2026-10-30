import json
import re
import sqlite3
import unicodedata
from contextlib import closing

from .errors import MemoryError
from .index import _path, ensure_index_current
from .models import SearchHit, SearchPage


def search_memory(store, request):
    with store.mutex:
        report = ensure_index_current(store)
        tokens = re.findall(
            r"[^\W_]+", unicodedata.normalize("NFC", request.query), re.UNICODE
        )
        if not tokens:
            raise MemoryError("VALIDATION_ERROR", "Query needs at least one word")
        query = " AND ".join('"' + token + '"' for token in tokens)
        items = []
        with closing(sqlite3.connect(_path(store))) as db:
            rows = db.execute(
                "SELECT records.ref,records.layer,records.topics,records.data,fts.title,snippet(fts,2,'[',']','…',24),bm25(fts) FROM fts JOIN records ON fts.ref=records.ref WHERE fts MATCH ? ORDER BY bm25(fts),records.ref",
                (query,),
            ).fetchall()
        for ref, layer, topics, data, title, snippet, score in rows:
            topics = json.loads(topics)
            if request.layers is not None and layer not in request.layers:
                continue
            if request.topic_ids is not None and not set(
                request.topic_ids
            ).intersection(topics):
                continue
            items.append(
                SearchHit(
                    ref=ref,
                    layer=layer,
                    topic_ids=topics,
                    title=title,
                    snippet=snippet,
                    score=score,
                    **json.loads(data),
                )
            )
            if len(items) >= request.limit:
                break
        return SearchPage(items=items, index_revision=report.source_revision)
