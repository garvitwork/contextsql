"""User-editable business glossary: term -> definition + SQL snippet + tables."""
from .config import GLOSS, load_json, save_json

def load():
    return load_json(GLOSS, {})

def add(term, definition, sql, tables=()):
    g = load()
    g[term.lower()] = {"definition": definition, "sql": sql, "tables": list(tables)}
    save_json(GLOSS, g)

def remove(term):
    g = load()
    found = g.pop(term.lower(), None) is not None
    save_json(GLOSS, g)
    return found

def merge_imported(rows):
    """rows: (term, definition, sql, tables) - never overwrites entries the user already has."""
    g, added = load(), 0
    for term, definition, sql, tables in rows:
        if term.lower() not in g:
            g[term.lower()] = {"definition": definition, "sql": sql,
                               "tables": [t.strip() for t in (tables or "").split(",") if t.strip()]}
            added += 1
    save_json(GLOSS, g)
    return added
