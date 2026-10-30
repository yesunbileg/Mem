"""Store user-defined L1 abbreviations without hard-coded marker prefixes."""

import json
import re
import unicodedata


def get_shorthand(store):
    row = store.db.execute(
        "SELECT value FROM metadata WHERE key='shorthand'"
    ).fetchone()
    return json.loads(row[0]) if row else {}


def expand_for_index(text, meanings):
    """Keep original code searchable and add meaning only at token boundaries."""
    if not meanings:
        return text
    normalized = unicodedata.normalize("NFC", text)
    codes = sorted(meanings, key=len, reverse=True)
    pattern = re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(code) for code in codes) + r")(?!\w)"
    )
    return pattern.sub(lambda m: m.group() + " " + meanings[m.group()], normalized)


def expand_query(query, meanings):
    """An entire known code, including symbol-only codes, means its expansion."""
    normalized = unicodedata.normalize("NFC", query.strip())
    return meanings.get(normalized, query)
