"""Auto-built business glossary: detects common patterns in ANY schema (valid-status filters, revenue,
'without child', 'active', outcome rates) and can generate verified training examples from them."""
import re
from .names import singular, ABBR2FULL, PREFIXES
from .retrieve import name_alts, all_fks

BAD = ("cancel", "void", "reject", "fail", "refund", "return", "declin", "abandon", "delet", "invalid", "expire",
       "lost", "no_show", "drop", "default", "withdraw", "lapse", "churn")
GOOD = ("complet", "deliver", "paid", "resolv", "clos", "won", "approv", "done", "success", "checked", "arriv", "receiv", "hired")
STATUS = {"status", "statu", "state", "stage", "outcome", "sts"}
QTY = {"quantity", "qty"}
PRICE = {"price", "prc"}
PRICE2 = {"cost", "fare"}
DISC = {"discount", "disc"}
TEXT = ("CHAR", "TEXT", "ENUM", "STRING")
DATE = ("DATE", "TIME")
NUM = ("INT", "DECIMAL", "NUMERIC", "FLOAT", "DOUBLE", "REAL")
DISP = {"name", "title", "label", "company"}

def _flat(col):
    s = set()
    for a in name_alts(col): s |= a
    return s

def _is(meta, col, kinds):
    return any(k in meta["types"][col].upper() for k in kinds)

def _flag(meta, col):
    t = meta["types"][col].upper()
    return "TINYINT(1)" in t or "BOOL" in t or t.startswith("BIT")

def _keys(meta):
    return {c for fk in all_fks(meta) for c in fk["cols"]} | set(meta["pk"])

def cols_of(meta, tokens, kinds=None, exclude=()):
    return [c for c in meta["columns"] if c not in exclude and _flat(c) & tokens
            and (kinds is None or _is(meta, c, kinds)) and not _flag(meta, c)]

def label(name, sing=False):
    n = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    parts = [p for p in re.split(r"[_\W]+", n.lower()) if p]
    if len(parts) > 1 and parts[0] in PREFIXES: parts = parts[1:]
    words = [ABBR2FULL.get(p, p) for p in parts]
    if sing and words: words[-1] = singular(words[-1])
    return " ".join(words)

class Labels:
    """Plain-English names. With synthetic metadata they are exact; otherwise derived from the physical names."""
    def __init__(self, meta=None):
        self.m = {}
        if meta:
            for T in meta["tables"].values():
                self.m[T["phys"]] = (T["label_sg"], T["label_pl"])
                for c in T["cols"]: self.m[(T["phys"], c["phys"])] = c["label"]
    def tbl(self, t):
        if t in self.m: return self.m[t]
        sg = label(t, True); return sg, sg + "s"
    def col(self, t, c): return self.m.get((t, c)) or label(c)

def disp_col(meta):
    for c in meta["columns"]:
        if _is(meta, c, TEXT) and _flat(c) & DISP: return c
    for c in meta["columns"]:
        if _is(meta, c, TEXT): return c
    return meta["pk"][0] if meta["pk"] else meta["columns"][0]

def cat_cols(know, t, exclude=()):
    return [c for c in know["tables"][t]["columns"] if f"{t}.{c}" in know.get("values", {}) and c not in exclude]

def build(know, labels=None):
    """-> {term: entry}. entry: kind, term, definition, tpl (with {a} alias slot), sql, tables, params."""
    L = labels or Labels()
    T, E, valid = know["tables"], {}, {}
    for t, m in T.items():                                    # 1) valid-status filter
        for col in cols_of(m, STATUS, TEXT):
            vals = know.get("values", {}).get(f"{t}.{col}", [])
            bad = sorted({v.lower() for v in vals if any(b in v.lower() for b in BAD)})
            if bad:
                sg, _ = L.tbl(t); term = f"valid {sg}"
                tpl = "LOWER({a}.%s) NOT IN (%s)" % (col, ", ".join(f"'{b}'" for b in bad))
                valid[t] = dict(col=col, tpl=tpl, term=term)
                E[term] = dict(kind="valid", term=term, table=t, col=col, tpl=tpl, sql=tpl.format(a="t"), tables=[t],
                               definition=f"A {sg} whose {L.col(t, col)} is not {' or '.join(bad)} (compare in lowercase).")
                break
    for t, m in T.items():                                    # 2) revenue
        if "revenue" in E: break
        ex = _keys(m)
        qty, pr = cols_of(m, QTY, NUM, ex), cols_of(m, PRICE, NUM, ex) or cols_of(m, PRICE2, NUM, ex)
        if not (qty and pr): continue
        disc = cols_of(m, DISC, NUM)
        expr = ("SUM({i}.%s * {i}.%s * (1 - COALESCE({i}.%s,0)/100))" % (qty[0], pr[0], disc[0])) if disc \
            else "SUM({i}.%s * {i}.%s)" % (qty[0], pr[0])
        par = next((fk for fk in all_fks(m) if fk["ref_table"] in valid and len(fk["cols"]) == 1), None)
        sg, pl = L.tbl(t)
        defi = f"Sum of {L.col(t, qty[0])} times {L.col(t, pr[0])}{' after discount' if disc else ''}, "
        if par:
            psg, _ = L.tbl(par["ref_table"]); defi += f"for valid {psg}s only."
        else:
            defi += f"over all {pl}."
        E["revenue"] = dict(kind="revenue_A", term="revenue", table=t, tpl=expr, sql=expr.format(i="i"), definition=defi,
                            tables=[t] + ([par["ref_table"]] if par else []), par=par, qty=qty[0], price=pr[0])
    if "revenue" not in E:
        for t, m in T.items():
            qty = cols_of(m, QTY, NUM, _keys(m))
            if not qty: continue
            for fk in all_fks(m):
                M = fk["ref_table"]
                if M not in T or len(fk["cols"]) != 1: continue
                mp = cols_of(T[M], PRICE, NUM, _keys(T[M])) or cols_of(T[M], PRICE2, NUM, _keys(T[M]))
                if mp:
                    expr = "SUM({i}.%s * {m}.%s)" % (qty[0], mp[0])
                    E["revenue"] = dict(kind="revenue_B", term="revenue", table=t, tpl=expr, sql=expr.format(i="i", m="m"),
                                        definition=f"Sum of {L.col(t, qty[0])} times {L.col(M, mp[0])} of the linked {L.tbl(M)[0]}.",
                                        tables=[t, M], par=fk, qty=qty[0], price=mp[0], pt=M)
                    break
            if "revenue" in E: break
    n_wo = n_act = 0
    for ct, m in T.items():                                   # 3) without-child, 4) active parent
        for fk in all_fks(m):
            P = fk["ref_table"]
            if P not in T or len(fk["cols"]) != 1 or P == ct: continue
            psg, ppl = L.tbl(P); csg, cpl = L.tbl(ct)
            term = f"{psg} without {csg}"
            if term not in E and n_wo < 6:
                n_wo += 1
                tpl = "NOT EXISTS (SELECT 1 FROM %s c WHERE c.%s = {a}.%s)" % (ct, fk["cols"][0], fk["ref_cols"][0])
                E[term] = dict(kind="without", term=term, table=P, child=ct, fk=fk, tpl=tpl, sql=tpl.format(a="p"),
                               tables=[P, ct], definition=f"A {psg} that has no {csg} records.")
            dcols = [c for c in m["columns"] if _is(m, c, DATE) and c not in _keys(m)]
            term = f"active {psg}"
            if dcols and term not in E and n_act < 6:
                n_act += 1
                tpl = "{a}.%s >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)" % dcols[0]
                E[term] = dict(kind="active", term=term, table=P, child=ct, fk=fk, date=dcols[0], tpl=tpl, sql=tpl.format(a="c"),
                               tables=[P, ct], definition=f"A {psg} with at least one {csg} in the last 90 days (by {L.col(ct, dcols[0])}).")
    for t, m in T.items():                                    # 5) outcome share
        for col in cols_of(m, STATUS, TEXT):
            vals = know.get("values", {}).get(f"{t}.{col}", [])
            good = [v for v in vals if any(g in v.lower() for g in GOOD)]
            if good:
                v, sg = good[0], L.tbl(t)[0]; term = f"{v.lower().replace('_', ' ')} {sg}"
                tpl = "ROUND(100 * SUM({a}.%s = '%s') / COUNT(*), 2)" % (col, v)
                E.setdefault(term, dict(kind="outcome", term=term, table=t, col=col, value=v, tpl=tpl, sql=tpl.format(a="t"),
                                        tables=[t], definition=f"Percentage of {L.tbl(t)[1]} whose {L.col(t, col)} is {v}."))
                break
    return E

def probe_sql(e):
    k = e["kind"]
    if k == "valid": return f"SELECT COUNT(*) FROM {e['table']} t WHERE {e['tpl'].format(a='t')}"
    if k == "revenue_A": return f"SELECT {e['tpl'].format(i='i')} FROM {e['table']} i"
    if k == "revenue_B":
        fk = e["par"]; return f"SELECT {e['tpl'].format(i='i', m='m')} FROM {e['table']} i JOIN {e['pt']} m ON i.{fk['cols'][0]} = m.{fk['ref_cols'][0]}"
    if k == "without": return f"SELECT COUNT(*) FROM {e['table']} p WHERE {e['tpl'].format(a='p')}"
    if k == "active":
        fk = e["fk"]; return (f"SELECT COUNT(*) FROM {e['table']} p JOIN {e['child']} c ON c.{fk['cols'][0]} = p.{fk['ref_cols'][0]} "
                              f"WHERE {e['tpl'].format(a='c')}")
    return f"SELECT {e['tpl'].format(a='t')} FROM {e['table']} t"

def build_verified(know, engine):
    """Entries whose probe query actually runs on this database, in the public glossary format."""
    out = {}
    with engine.connect() as c:
        for term, e in build(know).items():
            try:
                c.exec_driver_sql(probe_sql(e).replace("%", "%%") if engine.dialect.name in ("mysql", "postgresql") else probe_sql(e)).fetchall()
            except Exception:
                continue
            out[term] = dict(definition=e["definition"], sql=e["sql"], tables=e["tables"], auto=True)
    return out

def examples(know, labels, entries):
    """Training examples that use the glossary entries. -> [{family, variants, sql, tables, used, terms, req, extra}]"""
    L, T, out = labels, know["tables"], []
    def add(fam, variants, sql, tables, terms, used=()):
        out.append(dict(family=fam, variants=variants, sql=" ".join(sql.split()), tables=list(dict.fromkeys(tables)),
                        used=list(used), terms=list(terms), req=[], extra=False))
    for term, e in entries.items():
        k, t = e["kind"], e["table"]
        sg, pl = L.tbl(t)
        if k == "valid":
            f = e["tpl"].format(a="t"); m = T[t]
            add("gl_valid_count", [f"How many valid {pl} are there?", f"Number of valid {pl}", f"Count the valid {pl}"],
                f"SELECT COUNT(*) FROM {t} t WHERE {f}", [t], [term], [f"{t}.{e['col']}"])
            for c in cat_cols(know, t, {e["col"]})[:2]:
                add("gl_valid_group", [f"Number of valid {pl} per {L.col(t, c)}", f"How many valid {pl} for each {L.col(t, c)}?"],
                    f"SELECT t.{c}, COUNT(*) AS n FROM {t} t WHERE {f} GROUP BY t.{c} ORDER BY n DESC", [t], [term], [f"{t}.{c}"])
            for n in [c for c in m["columns"] if _is(m, c, NUM) and not _flag(m, c) and c not in _keys(m)][:2]:
                add("gl_valid_sum", [f"Total {L.col(t, n)} of valid {pl}", f"What is the total {L.col(t, n)} across valid {pl}?"],
                    f"SELECT ROUND(SUM(t.{n}),2) AS total FROM {t} t WHERE {f}", [t], [term])
            for d in [c for c in m["columns"] if _is(m, c, DATE) and c not in _keys(m)][:1]:
                for days in (90, 365):
                    add("gl_valid_recent", [f"How many valid {pl} in the last {days} days?", f"Number of valid {pl} within the past {days} days"],
                        f"SELECT COUNT(*) FROM {t} t WHERE {f} AND t.{d} >= DATE_SUB(CURDATE(), INTERVAL {days} DAY)", [t], [term])
        elif k in ("revenue_A", "revenue_B"):
            fk, par = e.get("par"), e.get("par")
            ex = e["tpl"].format(i="i", m="m")
            if k == "revenue_A":
                join, where, ptab, terms = f"{t} i", "", None, [term]
                if fk:
                    ptab = fk["ref_table"]; vt = next(x for x in entries.values() if x["kind"] == "valid" and x["table"] == ptab)
                    join = f"{t} i JOIN {ptab} p ON i.{fk['cols'][0]} = p.{fk['ref_cols'][0]}"
                    where = " WHERE " + vt["tpl"].format(a="p"); terms = [term, vt["term"]]
            else:
                ptab = e["pt"]; join = f"{t} i JOIN {ptab} m ON i.{fk['cols'][0]} = m.{fk['ref_cols'][0]}"; where, terms = "", [term]
            al = "p" if k == "revenue_A" else "m"
            add("gl_revenue", ["What is our total revenue?", "Total revenue", "How much revenue have we made?"],
                f"SELECT ROUND({ex},2) AS revenue FROM {join}{where}", [t] + ([ptab] if ptab else []), terms)
            if ptab:
                pm = T[ptab]
                for c in cat_cols(know, ptab)[:2]:
                    if k == "revenue_A" and c == next(x for x in entries.values() if x["kind"] == "valid" and x["table"] == ptab)["col"]: continue
                    add("gl_revenue_group", [f"Revenue by {L.col(ptab, c)}", f"Show revenue per {L.col(ptab, c)}"],
                        f"SELECT {al}.{c}, ROUND({ex},2) AS revenue FROM {join}{where} GROUP BY {al}.{c} ORDER BY revenue DESC", [t, ptab], terms, [f"{ptab}.{c}"])
                if k == "revenue_A":
                    d, pk = disp_col(pm), (pm["pk"] or [pm["columns"][0]])[0]
                    psg, ppl = L.tbl(ptab)
                    for kk in (3, 5, 10):
                        add("gl_revenue_top", [f"Top {kk} {ppl} by revenue", f"Which {kk} {ppl} bring in the most revenue?"],
                            f"SELECT p.{d}, ROUND({ex},2) AS revenue FROM {join}{where} GROUP BY p.{pk}, p.{d} ORDER BY revenue DESC LIMIT {kk}", [t, ptab], terms)
                    for dc in [c for c in pm["columns"] if _is(pm, c, DATE) and c not in _keys(pm)][:1]:
                        for days in (90, 365):
                            w2 = (where + " AND " if where else " WHERE ") + f"p.{dc} >= DATE_SUB(CURDATE(), INTERVAL {days} DAY)"
                            add("gl_revenue_recent", [f"Revenue in the last {days} days", f"How much revenue did we make in the past {days} days?"],
                                f"SELECT ROUND({ex},2) AS revenue FROM {join}{w2}", [t, ptab], terms)
        elif k == "without":
            P, C, fk = t, e["child"], e["fk"]; psg, ppl = L.tbl(P); csg, cpl = L.tbl(C); d = disp_col(T[P])
            f = e["tpl"].format(a="p")
            add("gl_without_count", [f"How many {ppl} have no {cpl}?", f"Number of {ppl} without any {cpl}", f"Count {ppl} that have never had a {csg}"],
                f"SELECT COUNT(*) FROM {P} p WHERE {f}", [P, C], [term])
            for kk in (5, 10):
                add("gl_without_list", [f"List {kk} {ppl} without {cpl}", f"Show {kk} {ppl} that have no {cpl}"],
                    f"SELECT p.{d} FROM {P} p WHERE {f} LIMIT {kk}", [P, C], [term])
        elif k == "active":
            P, C, fk = t, e["child"], e["fk"]; psg, ppl = L.tbl(P); csg, cpl = L.tbl(C)
            f = e["tpl"].format(a="c"); pk = fk["ref_cols"][0]
            base = f"FROM {P} p JOIN {C} c ON c.{fk['cols'][0]} = p.{pk} WHERE {f}"
            add("gl_active_count", [f"How many active {ppl} do we have?", f"Number of active {ppl}", f"Count active {ppl}"],
                f"SELECT COUNT(DISTINCT p.{pk}) AS active {base}", [P, C], [term])
            for c2 in cat_cols(know, P)[:2]:
                add("gl_active_group", [f"Active {ppl} by {L.col(P, c2)}", f"How many active {ppl} per {L.col(P, c2)}?"],
                    f"SELECT p.{c2}, COUNT(DISTINCT p.{pk}) AS active {base} GROUP BY p.{c2} ORDER BY active DESC", [P, C], [term], [f"{P}.{c2}"])
        elif k == "outcome":
            v, col = e["value"], e["col"]; vtxt = v.replace("_", " ")
            add("gl_outcome_pct", [f"What percentage of {pl} are {vtxt}?", f"Share of {pl} that are {vtxt}", f"What is the {vtxt} rate of {pl}?"],
                f"SELECT ROUND(100 * SUM(t.{col} = '{v}') / COUNT(*), 2) AS pct FROM {t} t", [t], [term], [f"{t}.{col}"])
            for c in cat_cols(know, t, {col})[:1]:
                add("gl_outcome_group", [f"Percentage of {pl} that are {vtxt} by {L.col(t, c)}", f"{vtxt.capitalize()} rate of {pl} per {L.col(t, c)}"],
                    f"SELECT t.{c}, ROUND(100 * SUM(t.{col} = '{v}') / COUNT(*), 2) AS pct FROM {t} t GROUP BY t.{c} ORDER BY pct DESC", [t], [term], [f"{t}.{c}"])
    for t, m in T.items():                                    # flag columns (no glossary term needed)
        sg, pl = L.tbl(t)
        for c in [c for c in m["columns"] if _flag(m, c)][:2]:
            fl = re.sub(r"^is ", "", L.col(t, c))
            add("flag_count", [f"How many {pl} are {fl}?", f"Number of {pl} that are {fl}", f"Count the {fl} {pl}"],
                f"SELECT COUNT(*) FROM {t} WHERE {c} = 1", [t], [])
            add("flag_pct", [f"What percentage of {pl} are {fl}?", f"Share of {pl} that are {fl}"],
                f"SELECT ROUND(100 * AVG({c}), 2) AS pct FROM {t}", [t], [])
    return out
