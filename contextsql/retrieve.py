"""Pick the relevant tables, glossary entries and data notes for a question (no extra model needed)."""
import re

STOP = set("""the a an of in on by for per to from and or with without is are was were be our we us my me i you your
all any show list give get find what which who whom how many much top best most least highest lowest total number count
last past each every please can could tell about than then that this these those it its there their them do does did has have
had day days week weeks month months year years""".split())
GENERIC_COLS = {"id", "name", "date", "type", "value", "created", "updated", "at"}

def stem(w):
    if w.endswith("ies") and len(w) > 4: return w[:-3] + "y"
    if w.endswith("s") and len(w) > 3 and not w.endswith("ss"): return w[:-1]
    return w

def toks(text):
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and not w.isdigit()]

def name_toks(name):
    return {stem(p) for p in re.split(r"[_\W]+", name.lower()) if p}

def hit(name_tokens, q):
    """True if every name token appears in the question (prefix match handles dept/department)."""
    return bool(name_tokens) and all(
        any(t == w or (len(t) >= 4 and len(w) >= 4 and (w.startswith(t) or t.startswith(w))) for w in q)
        for t in name_tokens)

def select(question, know, gloss, max_tables=5):
    q = set(toks(question))
    qlow = question.lower()
    tables = know["tables"]
    score = {t: 0.0 for t in tables}
    hit_cols = set()

    for t, meta in tables.items():
        if hit(name_toks(t), q): score[t] += 4
        fk_cols = {c for fk in meta["fks"] for c in fk["cols"]}
        for col in meta["columns"]:
            if col in fk_cols: continue
            ct = name_toks(col) - GENERIC_COLS
            if ct and hit(ct, q):
                score[t] += 1; hit_cols.add(f"{t}.{col}")
    for key, vals in know.get("values", {}).items():
        t = key.split(".")[0]
        for v in vals:
            vt = set(toks(v))
            if vt and vt <= q:
                score[t] += 2; hit_cols.add(key)

    # glossary: term words all present in the question
    matched = [k for k, g in gloss.items() if set(toks(k)) and set(toks(k)) <= q]
    for k in list(matched):                      # pull in terms this definition depends on (e.g. 'valid order')
        d = gloss[k]["definition"].lower()
        matched += [o for o in gloss if o not in matched and o != k and o in d]
    for k in matched:
        for t in gloss[k].get("tables", []):
            if t in score: score[t] += 5

    chosen = [t for t, s in sorted(score.items(), key=lambda x: -x[1]) if s > 0][:max_tables]
    if not chosen:   # nothing matched: fall back to the biggest tables
        chosen = sorted(tables, key=lambda t: -tables[t].get("rows", 0))[:min(4, len(tables))]

    if len(chosen) <= 1:   # few tables matched: also include their parent tables so joins stay possible
        for t in list(chosen):
            for fk in tables[t]["fks"]:
                if fk["ref_table"] in tables and fk["ref_table"] not in chosen and len(chosen) < 4:
                    chosen.append(fk["ref_table"])

    # add bridge tables that connect two chosen tables through foreign keys
    for t, meta in tables.items():
        if t in chosen: continue
        links = {fk["ref_table"] for fk in meta["fks"]} | {o for o, m in tables.items()
                                                           if any(fk["ref_table"] == t for fk in m["fks"])}
        if len(links & set(chosen)) >= 2 and len(chosen) < max_tables + 1:
            chosen.append(t)

    notes = []
    for n in know.get("notes", []):
        if n["table"] not in chosen: continue
        if n["kind"] in ("variants", "null") or f"{n['table']}.{n['column']}" in hit_cols:
            notes.append(n)
    return {"tables": chosen, "glossary": matched, "notes": notes, "scores": score}
