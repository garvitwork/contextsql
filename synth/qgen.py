"""Schema-driven question -> SQL generator. Questions use plain-English labels; SQL uses the physical (cryptic) names."""
import itertools

def _disp(T):
    for c in T["cols"]:
        if c["kind"] in ("name", "label"):
            return c["phys"]
    return T["pk"]

def _num(T):
    return [c for c in T["cols"] if c["kind"] in ("money", "int")]

def _cats(T):
    return [c for c in T["cols"] if c["kind"] == "cat"]

def _v(s):
    return s.replace("_", " ")

def candidates(meta):
    """Yield dicts: family, variants (list of question strings), sql, tables (physical), used (table.col list)."""
    TB = meta["tables"]
    out = []
    def add(family, variants, sql, tables, used=(), extra=False, req=()):
        out.append(dict(family=family, variants=variants, sql=sql, tables=tables, used=list(used),
                        extra=extra, req=list(req), terms=[]))

    for lt, T in TB.items():
        p, pl, sg = T["phys"], T["label_pl"], T["label_sg"]
        add("count_all", [f"How many {pl} are there?", f"Total number of {pl}", f"Count of {pl}"],
            f"SELECT COUNT(*) FROM {p}", [p])
        for c in _cats(T):
            opts = c["args"].split("|")
            for v in opts[:4]:
                add("count_cat", [f"How many {pl} have {c['label']} {_v(v)}?", f"Number of {pl} with {c['label']} '{_v(v)}'",
                                  f"Count the {pl} whose {c['label']} is {_v(v)}"],
                    f"SELECT COUNT(*) FROM {p} WHERE {c['phys']} = '{v}'", [p], [f"{p}.{c['phys']}"])
            add("group_count", [f"Number of {pl} per {c['label']}", f"Count {pl} by {c['label']}", f"How many {pl} for each {c['label']}?"],
                f"SELECT {c['phys']}, COUNT(*) AS n FROM {p} GROUP BY {c['phys']} ORDER BY n DESC", [p], [f"{p}.{c['phys']}"])
            add("distinct_count", [f"How many different {c['label']} values do {pl} have?", f"Number of distinct {c['label']} among {pl}"],
                f"SELECT COUNT(DISTINCT {c['phys']}) FROM {p}", [p], [f"{p}.{c['phys']}"])
        for n in _num(T):
            for fn, w in [("SUM", "total"), ("AVG", "average"), ("MAX", "highest"), ("MIN", "lowest")]:
                add("agg", [f"What is the {w} {n['label']} of {pl}?", f"{w.capitalize()} {n['label']} across all {pl}", f"Find the {w} {n['label']} among {pl}"],
                    f"SELECT {'ROUND(' + fn + '(' + n['phys'] + '),2)' if fn in ('SUM', 'AVG') else fn + '(' + n['phys'] + ')'} FROM {p}", [p])
            for c in _cats(T):
                add("group_agg", [f"Average {n['label']} by {c['label']}", f"What is the average {n['label']} for each {c['label']} of {pl}?"],
                    f"SELECT {c['phys']}, ROUND(AVG({n['phys']}),2) AS avg_value FROM {p} GROUP BY {c['phys']} ORDER BY avg_value DESC", [p], [f"{p}.{c['phys']}"])
                add("group_sum", [f"Total {n['label']} per {c['label']}", f"Sum of {n['label']} grouped by {c['label']} for {pl}"],
                    f"SELECT {c['phys']}, ROUND(SUM({n['phys']}),2) AS total_value FROM {p} GROUP BY {c['phys']} ORDER BY total_value DESC", [p], [f"{p}.{c['phys']}"])
            for k in (3, 5, 10):
                add("top_n", [f"Top {k} {pl} by {n['label']}", f"Which {k} {pl} have the highest {n['label']}?", f"List the {k} {pl} with the largest {n['label']}"],
                    f"SELECT {_disp(T)}, {n['phys']} FROM {p} ORDER BY {n['phys']} DESC LIMIT {k}", [p])
        attrs_t = [a for a in T["cols"] if a["kind"] in ("cat", "city", "email") and a["phys"] != _disp(T)]
        for n in _num(T)[:2]:
            for a1, a2 in list(itertools.combinations(attrs_t, 2))[:3]:
                for k in (3, 5):
                    add("top_n_with", [f"Top {k} {pl} by {n['label']} with their {a1['label']} and {a2['label']}",
                                       f"give top {k} {pl} with highest {n['label']} with {a1['label']} and {a2['label']}"],
                        f"SELECT {_disp(T)}, {a1['phys']}, {a2['phys']}, {n['phys']} FROM {p} ORDER BY {n['phys']} DESC LIMIT {k}", [p], extra=True, req=[a1['phys'], a2['phys']])
        for c in T["cols"]:
            if c["nullable"]:
                add("null_count", [f"How many {pl} have no {c['label']}?", f"Number of {pl} missing a {c['label']}", f"Count {pl} without {c['label']}"],
                    f"SELECT COUNT(*) FROM {p} WHERE {c['phys']} IS NULL", [p])
            if c["kind"] == "date":
                for d in (90, 180, 365):
                    add("date_recent", [f"How many {pl} have {c['label']} in the last {d} days?", f"Number of {pl} with a {c['label']} within the past {d} days"],
                        f"SELECT COUNT(*) FROM {p} WHERE {c['phys']} >= DATE_SUB(CURDATE(), INTERVAL {d} DAY)", [p])
        # joins to parents
        for c in T["cols"]:
            if c["kind"] != "fk": continue
            P = TB[c["parent"]]; pp = P["phys"]
            on = f"c.{c['phys']} = p.{P['pk']}"
            add("join_count", [f"How many {pl} does each {P['label_sg']} have?", f"Number of {pl} per {P['label_sg']}"],
                f"SELECT p.{_disp(P)}, COUNT(*) AS n FROM {p} c JOIN {pp} p ON {on} GROUP BY p.{P['pk']}, p.{_disp(P)} ORDER BY n DESC", [p, pp])
            for k in (3, 5, 10):
                add("join_top_count", [f"Top {k} {P['label_pl']} by number of {pl}", f"Which {k} {P['label_pl']} have the most {pl}?"],
                    f"SELECT p.{_disp(P)}, COUNT(*) AS n FROM {p} c JOIN {pp} p ON {on} GROUP BY p.{P['pk']}, p.{_disp(P)} ORDER BY n DESC LIMIT {k}", [p, pp])
            for k in (2, 5, 10):
                add("join_having", [f"Which {P['label_pl']} have more than {k} {pl}?", f"List {P['label_pl']} with over {k} {pl}"],
                    f"SELECT p.{_disp(P)}, COUNT(*) AS n FROM {p} c JOIN {pp} p ON {on} GROUP BY p.{P['pk']}, p.{_disp(P)} HAVING COUNT(*) > {k} ORDER BY n DESC", [p, pp])
            for n in _num(T):
                for k in (3, 5):
                    add("join_top_sum", [f"Top {k} {P['label_pl']} by total {n['label']} of their {pl}", f"Which {k} {P['label_pl']} have the highest total {n['label']} of {pl}?"],
                        f"SELECT p.{_disp(P)}, ROUND(SUM(c.{n['phys']}),2) AS total FROM {p} c JOIN {pp} p ON {on} GROUP BY p.{P['pk']}, p.{_disp(P)} ORDER BY total DESC LIMIT {k}", [p, pp])
                add("join_sum", [f"Total {n['label']} of {pl} per {P['label_sg']}", f"Sum of {n['label']} for each {P['label_sg']}'s {pl}"],
                    f"SELECT p.{_disp(P)}, ROUND(SUM(c.{n['phys']}),2) AS total FROM {p} c JOIN {pp} p ON {on} GROUP BY p.{P['pk']}, p.{_disp(P)} ORDER BY total DESC", [p, pp])
            for pc in _cats(P):
                for v in pc["args"].split("|")[:3]:
                    add("join_filter", [f"How many {pl} belong to {P['label_pl']} with {pc['label']} {_v(v)}?", f"Count {pl} of {P['label_pl']} whose {pc['label']} is {_v(v)}"],
                        f"SELECT COUNT(*) FROM {p} c JOIN {pp} p ON {on} WHERE p.{pc['phys']} = '{v}'", [p, pp], [f"{pp}.{pc['phys']}"])
            attrs = [a for a in P["cols"] if a["kind"] in ("cat", "city", "email") and a["phys"] != _disp(P)]
            for n in _num(T)[:2]:
                for a1, a2 in list(itertools.combinations(attrs, 2))[:3]:
                    for k in (3, 5, 10):
                        add("join_top_sum_with", [f"Top {k} {P['label_pl']} by total {n['label']} of {pl} with their {a1['label']} and {a2['label']}",
                                                  f"give top {k} {P['label_pl']} with highest {n['label']} of {pl} with {a1['label']} and {a2['label']}"],
                            f"SELECT p.{_disp(P)}, p.{a1['phys']}, p.{a2['phys']}, ROUND(SUM(c.{n['phys']}),2) AS total FROM {p} c JOIN {pp} p ON {on} GROUP BY p.{P['pk']}, p.{_disp(P)}, p.{a1['phys']}, p.{a2['phys']} ORDER BY total DESC LIMIT {k}",
                            [p, pp], extra=True, req=[a1['phys'], a2['phys']])
                for a1, a2 in list(itertools.combinations(attrs, 2))[:2]:
                    add("join_top1_with", [f"Which {P['label_sg']} has the highest total {n['label']} of {pl}, and what is their {a1['label']} and {a2['label']}?",
                                           f"which {P['label_sg']} has highest {n['label']} of {pl} in which {a1['label']} and {a2['label']}"],
                        f"SELECT p.{_disp(P)}, p.{a1['phys']}, p.{a2['phys']}, ROUND(SUM(c.{n['phys']}),2) AS total FROM {p} c JOIN {pp} p ON {on} GROUP BY p.{P['pk']}, p.{_disp(P)}, p.{a1['phys']}, p.{a2['phys']} ORDER BY total DESC LIMIT 1",
                        [p, pp], extra=True, req=[a1['phys'], a2['phys']])
            # two-hop: grandchild -> child -> parent
            for g_lt, G in TB.items():
                for gc in G["cols"]:
                    if gc["kind"] == "fk" and gc["parent"] == lt:
                        for n in _num(G):
                            add("two_hop_sum", [f"Total {n['label']} of {G['label_pl']} per {P['label_sg']}", f"How much {n['label']} do {G['label_pl']} add up to for each {P['label_sg']}?"],
                                f"SELECT p.{_disp(P)}, ROUND(SUM(g.{n['phys']}),2) AS total FROM {G['phys']} g JOIN {p} c ON g.{gc['phys']} = c.{T['pk']} JOIN {pp} p ON {on} GROUP BY p.{P['pk']}, p.{_disp(P)} ORDER BY total DESC LIMIT 10",
                                [G["phys"], p, pp])
    return out

def generate(meta, engine, rng, per_family=7):
    """Run every candidate, keep those that execute and return data, cap per family."""
    by_fam = {}
    for cnd in candidates(meta):
        by_fam.setdefault(cnd["family"], []).append(cnd)
    result = []
    with engine.connect() as c:
        for fam, items in by_fam.items():
            rng.shuffle(items)
            kept = 0
            for it in items:
                if kept >= per_family: break
                try:
                    rows = c.exec_driver_sql(it["sql"]).fetchall()
                except Exception:
                    continue
                if not rows or all(v is None for v in rows[0]): continue
                kept += 1
                result.append(dict(it, question=rng.choice(it["variants"])))
    return result
