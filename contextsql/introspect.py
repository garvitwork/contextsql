"""Read schema + profile the data (null rates, categorical values, near-duplicate spellings)."""
import re, difflib
from sqlalchemy import inspect

TEXT_HINTS = ("CHAR", "TEXT", "ENUM", "STRING", "CLOB")
SAMPLE_ABOVE, SAMPLE_SIZE = 200_000, 100_000

def clean_mysql_ddl(raw):
    raw = raw.replace("`", "")
    lines = raw.split("\n")
    head, body = lines[0], [l.strip().rstrip(",") for l in lines[1:-1]]
    body = [l for l in body if not l.startswith("KEY ") and not l.startswith("UNIQUE KEY")]
    body = [re.sub(r"\s+(CHARACTER SET \w+|COLLATE \w+)", "", l) for l in body]
    body = [re.sub(r"\s+DEFAULT NULL", "", l) for l in body]
    return head + "\n  " + ",\n  ".join(body) + "\n);"

def col_type(engine, col):
    try:
        return str(col["type"].compile(dialect=engine.dialect))
    except Exception:
        return "UNKNOWN"

def ddl_for(engine, insp, table):
    if engine.dialect.name == "mysql":
        with engine.connect() as c:
            raw = c.exec_driver_sql(f"SHOW CREATE TABLE `{table}`").fetchone()[1]
        return clean_mysql_ddl(raw)
    lines = []
    for col in insp.get_columns(table):
        lines.append(f"{col['name']} {col_type(engine, col)}" + ("" if col.get("nullable", True) else " NOT NULL"))
    pk = insp.get_pk_constraint(table).get("constrained_columns") or []
    if pk: lines.append(f"PRIMARY KEY ({', '.join(pk)})")
    for fk in insp.get_foreign_keys(table):
        lines.append(f"FOREIGN KEY ({', '.join(fk['constrained_columns'])}) REFERENCES "
                     f"{fk['referred_table']} ({', '.join(fk['referred_columns'])})")
    return f"CREATE TABLE {table} (\n  " + ",\n  ".join(lines) + "\n);"

def similar_groups(values, threshold=0.9):
    """Find values that look like spelling/case variants of each other."""
    flagged = set()
    for i, a in enumerate(values):
        for b in values[i + 1:]:
            if a.lower() == b.lower() or difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold:
                flagged |= {a, b}
    return flagged

def profile(engine, tables, max_distinct=30):
    """Returns (notes, values). notes: [{table, column, kind, text}], values: {'table.col': [..]}"""
    q = engine.dialect.identifier_preparer.quote
    notes, values = [], {}
    with engine.connect() as c:
        for t, meta in tables.items():
            qt = q(t)
            n = c.exec_driver_sql(f"SELECT COUNT(*) FROM {qt}").scalar() or 0
            meta["rows"] = int(n)
            if n == 0:
                continue
            src = qt if n <= SAMPLE_ABOVE else f"(SELECT * FROM {qt} LIMIT {SAMPLE_SIZE}) AS s"
            cols = meta["columns"]
            is_text = {col: any(h in meta["types"][col].upper() for h in TEXT_HINTS) for col in cols}
            parts = [f"SUM(CASE WHEN {q(col)} IS NULL THEN 1 ELSE 0 END)" for col in cols]
            tcols = [col for col in cols if is_text[col]]
            parts += [f"COUNT(DISTINCT {q(col)})" for col in tcols]
            row = c.exec_driver_sql(f"SELECT COUNT(*), {', '.join(parts)} FROM {src}").fetchone()
            total, nulls, distincts = row[0] or 1, row[1:1 + len(cols)], row[1 + len(cols):]
            for col, nl in zip(cols, nulls):
                pct = 100 * (nl or 0) / total
                if 1 <= pct < 100 and col not in meta["pk"]:
                    notes.append(dict(table=t, column=col, kind="null",
                                      text=f"{t}.{col} can be NULL ({pct:.0f}% of rows); use COALESCE when aggregating."))
            for col, d in zip(tcols, distincts):
                if not d or d > max_distinct:
                    continue
                rows = c.exec_driver_sql(
                    f"SELECT {q(col)}, COUNT(*) FROM {src} WHERE {q(col)} IS NOT NULL "
                    f"GROUP BY {q(col)} ORDER BY COUNT(*) DESC LIMIT {max_distinct}").fetchall()
                vals = [str(r[0]) for r in rows]
                values[f"{t}.{col}"] = vals
                bad = similar_groups(vals)
                if bad:
                    notes.append(dict(table=t, column=col, kind="variants", text=(
                        f"{t}.{col} has inconsistent spelling/case ({', '.join(vals)}); "
                        f"compare with LOWER() and treat similar spellings as the same.")))
                elif d <= 12:
                    notes.append(dict(table=t, column=col, kind="values",
                                      text=f"{t}.{col} has values: {', '.join(vals)}."))
    return notes, values
