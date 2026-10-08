"""One-time scan: schema + data profile + glossary import -> ~/.contextsql/knowledge.json"""
from datetime import datetime, timezone
from sqlalchemy import inspect
from . import glossary
from .config import KNOW, save_json
from .introspect import ddl_for, col_type, profile

EXCLUDE_DEFAULT = {"query_log", "business_glossary"}

def learn(engine, exclude=EXCLUDE_DEFAULT, say=print):
    insp = inspect(engine)
    all_tables = insp.get_table_names()
    tables = {}
    for t in all_tables:
        if t in exclude:
            continue
        cols = insp.get_columns(t)
        tables[t] = {
            "ddl": ddl_for(engine, insp, t),
            "columns": [c["name"] for c in cols],
            "types": {c["name"]: col_type(engine, c) for c in cols},
            "pk": insp.get_pk_constraint(t).get("constrained_columns") or [],
            "fks": [{"cols": f["constrained_columns"], "ref_table": f["referred_table"],
                     "ref_cols": f["referred_columns"]} for f in insp.get_foreign_keys(t)],
        }
        say(f"  schema   {t} ({len(cols)} columns)")
    say("  profiling data ...")
    notes, values = profile(engine, tables)
    imported = 0
    if "business_glossary" in all_tables:
        with engine.connect() as c:
            rows = c.exec_driver_sql(
                "SELECT term, definition, sql_snippet, tables_used FROM business_glossary").fetchall()
        imported = glossary.merge_imported([tuple(r) for r in rows])
    know = {"dialect": engine.dialect.name, "tables": tables, "notes": notes, "values": values,
            "learned_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    save_json(KNOW, know)
    return know, imported
