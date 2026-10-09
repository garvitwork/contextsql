"""Pick relevant tables, columns, glossary entries and data notes for a question (no extra model needed)."""
import re
from .names import ABBR2FULL, PREFIXES

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

def name_alts(name):
    """[{alternatives for token 1}, {alternatives for token 2}, ...]  e.g. tbl_cust -> [{cust, customer}]"""
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    parts = [p for p in re.split(r"[_\W]+", name.lower()) if p]
    if len(parts) > 1 and parts[0] in PREFIXES: parts = parts[1:]
    out = []
    for p in parts:
        alt = {stem(p)}
        if p in ABBR2FULL: alt.add(stem(ABBR2FULL[p]))
        out.append(alt)
    return out

def skel(w):
    return w[0] + re.sub(r"[aeiou]", "", w[1:])

def tok_match(t, w):
    if t == w:
        return True
    if len(t) >= 4 and len(w) >= 4 and (w.startswith(t) or t.startswith(w)):
        return True
    return len(t) >= 4 and len(w) >= 5 and skel(w) == t      # cstmr == skeleton of "customer"

def hit(alts, q):
    return bool(alts) and all(any(tok_match(t, w) for t in alt for w in q) for alt in alts)

def all_fks(meta):
    return list(meta["fks"]) + list(meta.get("fks_inferred", []))

def select(question, know, gloss, max_tables=5):
    q = set(toks(question))
    tables = know["tables"]
    score = {t: 0.0 for t in tables}
    hit_cols = set()

    for t, meta in tables.items():
        if hit(name_alts(t), q): score[t] += 4
        fk_cols = {c for fk in all_fks(meta) for c in fk["cols"]}
        for col in meta["columns"]:
            if col in fk_cols: continue
            alts = [a for a in name_alts(col) if not (a & GENERIC_COLS)]
            if alts and hit(alts, q):
                score[t] += 1; hit_cols.add(f"{t}.{col}")
    for key, vals in know.get("values", {}).items():
        t = key.split(".")[0]
        for v in vals:
            vt = set(toks(v))
            if vt and vt <= q:
                score[t] += 2; hit_cols.add(key)

    matched = [k for k, g in gloss.items() if set(toks(k)) and set(toks(k)) <= q]
    for k in list(matched):
        d = gloss[k]["definition"].lower()
        matched += [o for o in gloss if o not in matched and o != k and o in d]
    for k in matched:
        for t in gloss[k].get("tables", []):
            if t in score: score[t] += 5

    chosen = [t for t, s in sorted(score.items(), key=lambda x: -x[1]) if s > 0][:max_tables]
    if not chosen:
        chosen = sorted(tables, key=lambda t: -tables[t].get("rows", 0))[:min(4, len(tables))]

    if len(chosen) <= 1:   # one table matched: include its parent tables so joins stay possible
        for t in list(chosen):
            for fk in all_fks(tables[t]):
                if fk["ref_table"] in tables and fk["ref_table"] not in chosen and len(chosen) < 3:
                    chosen.append(fk["ref_table"])

    for t, meta in tables.items():   # bridge tables connecting two chosen tables
        if t in chosen: continue
        links = {fk["ref_table"] for fk in all_fks(meta)} | {o for o, m in tables.items()
                                                             if any(fk["ref_table"] == t for fk in all_fks(m))}
        if len(links & set(chosen)) >= 2 and len(chosen) < max_tables + 1:
            chosen.append(t)

    notes = []
    for n in know.get("notes", []):
        if n["table"] not in chosen: continue
        if n["kind"] == "join":
            if n["ref_table"] in chosen: notes.append(n)
        elif n["kind"] in ("variants", "null") or f"{n['table']}.{n['column']}" in hit_cols:
            notes.append(n)

    # columns worth keeping when a table is too wide to show in full
    gtext = " ".join(gloss[k]["sql"] + " " + gloss[k]["definition"] for k in matched).lower()
    keep = {}
    for t in chosen:
        meta = tables[t]
        ks = set(meta["pk"]) | {c for fk in all_fks(meta) for c in fk["cols"]} | set(meta["columns"][:6])
        ks |= {c for c in meta["columns"] if f"{t}.{c}" in hit_cols or c.lower() in gtext}
        ks |= {n["column"] for n in notes if n["table"] == t}
        keep[t] = ks
    return {"tables": chosen, "glossary": matched, "notes": notes, "scores": score, "keep": keep}
