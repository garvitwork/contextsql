"""Create the synthetic databases in MySQL and return metadata (logical <-> physical names, labels)."""
import random, re
from datetime import date, timedelta
import pymysql
from contextsql.names import FULL2ABBR, singular
from .specs import SPECS, DB_STYLE, DB_DOMAIN, DB_PREFIX, parse

FIRST = "Alex Priya Rahul Maria Chen Omar Sofia Liam Aisha Noah Elena Raj Yuki Ivan Zara Leo Nina Sam Tara Kofi".split()
LAST = "Rao Smith Khan Garcia Wang Ali Kim Brown Patel Silva Novak Sato Jones Singh Lopez Meyer Ito Cruz Das Roy".split()
ADJ = "Blue Prime Rapid Solid Bright Grand Swift Noble Urban Alpha Delta Omega Silver Green Royal".split()
NOUN = "Harbor Summit Forge Meadow Bridge Tower Grove Vector Anchor Ridge Orbit Canyon Beacon Atlas Pixel".split()
CITIES = "Delhi Mumbai Pune London Leeds Berlin Austin Boston Tokyo Lagos Paris Toronto".split()

def _abbr(tok, mode):
    if not mode:
        return tok
    a = FULL2ABBR.get(tok) or FULL2ABBR.get(singular(tok))
    if a:
        return a
    if mode == "skeleton" and len(tok) >= 5:
        return tok[0] + re.sub(r"[aeiou]", "", tok[1:])
    return tok

def phys_table(logical, st):
    toks = logical.split("_")
    if st.get("singular") and not st["abbr"]:
        toks[-1] = singular(toks[-1])
    toks = [_abbr(t, st["abbr"]) for t in toks]
    return st["tbl"] + "_".join(toks)

def style_name(tokens, st, table_prefix=None):
    toks = [_abbr(t, st["abbr"]) for t in tokens]
    if st["col"] == "camel":
        return toks[0] + "".join(t.capitalize() for t in toks[1:])
    if st["col"] == "pascal":
        return "".join(t.capitalize() for t in toks)
    name = "_".join(toks)
    if st["col"] == "prefixed" and table_prefix:
        return f"{table_prefix}_{name}"
    return name

def build_meta(key):
    domain = DB_DOMAIN[key]
    st, spec = DB_STYLE[key], parse(SPECS[domain])
    meta = {"domain": domain, "key": key, "db": DB_PREFIX + key, "style": st, "tables": {}}
    for lt, cols in spec.items():
        sg = [singular(w) for w in lt.split("_")]
        prefix = FULL2ABBR.get(sg[0], sg[0][:4])
        pkname = "id" if st["pk"] == "id" else style_name(sg + ["id"], st)
        meta["tables"][lt] = dict(phys=phys_table(lt, st), pk=pkname, label_pl=lt.replace("_", " "),
                                  label_sg=" ".join(sg), cols=[], _prefix=prefix)
    for lt, cols in spec.items():
        T = meta["tables"][lt]
        for c in cols:
            c = dict(c)
            if c["kind"] == "fk":
                parent = meta["tables"][c["args"]]
                c["parent"] = c["args"]
                c["phys"] = parent["pk"] if st["pk"] == "table_id" else style_name(
                    [singular(w) for w in c["args"].split("_")] + ["id"], dict(st, col="snake" if st["col"] == "prefixed" else st["col"]))
                c["label"] = parent["label_sg"]
            else:
                c["phys"] = style_name(c["logical"].split("_"), st, T["_prefix"])
                c["label"] = c["logical"].replace("_", " ")
            T["cols"].append(c)
    return meta

SQLTYPE = dict(name="VARCHAR(100)", label="VARCHAR(100)", email="VARCHAR(120)", city="VARCHAR(60)", cat="VARCHAR(30)",
               date="DATE", money="DECIMAL(12,2)", int="INT", code="INT", flag="TINYINT(1)", fk="INT")

def _value(c, rng, n_parent):
    k, a = c["kind"], c["args"]
    if k == "name": return f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    if k == "label": return f"{rng.choice(ADJ)} {rng.choice(NOUN)} {rng.randint(1, 99)}"
    if k == "email": return f"{rng.choice(FIRST).lower()}{rng.randint(1, 999)}@example.com"
    if k == "city": return rng.choice(CITIES)
    if k == "money": lo, hi = map(float, a.split("-")); return round(rng.uniform(lo, hi), 2)
    if k in ("int", "code"): lo, hi = map(int, a.split("-")); return rng.randint(lo, hi)
    if k == "date": return date.today() - timedelta(days=rng.randint(1, int(float(a) * 365)))
    if k == "cat":
        opts = a.split("|"); return rng.choices(opts, weights=[len(opts) - i for i in range(len(opts))])[0]
    if k == "flag": return int(rng.random() < 0.6)
    if k == "fk": return rng.randint(1, n_parent)

def create_database(conn, key, seed=7):
    rng = random.Random(f"{seed}-{key}")
    meta = build_meta(key); st = meta["style"]
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {meta['db']}"); cur.execute(f"CREATE DATABASE {meta['db']}")
    cur.execute(f"USE {meta['db']}")
    sizes, depth = {}, {}
    for lt, T in meta["tables"].items():
        parents = [c["parent"] for c in T["cols"] if c["kind"] == "fk"]
        depth[lt] = 0 if not parents else 1 + max(depth[p] for p in parents)
        sizes[lt] = [60, 400, 800][min(depth[lt], 2)]
        defs = [f"{T['pk']} INT PRIMARY KEY"]
        for c in T["cols"]:
            defs.append(f"{c['phys']} {SQLTYPE[c['kind']]}" + ("" if c["nullable"] else " NOT NULL"))
            if c["kind"] == "fk" and st["fk_declared"]:
                defs.append(f"FOREIGN KEY ({c['phys']}) REFERENCES {meta['tables'][c['parent']]['phys']}({meta['tables'][c['parent']]['pk']})")
        cur.execute(f"CREATE TABLE {T['phys']} ({', '.join(defs)})")
        nulls = {c["phys"]: rng.uniform(0.08, 0.2) for c in T["cols"] if c["nullable"]}
        rows = []
        for i in range(1, sizes[lt] + 1):
            row = [i]
            for c in T["cols"]:
                v = None if (c["nullable"] and rng.random() < nulls[c["phys"]]) else _value(
                    c, rng, sizes.get(c.get("parent"), 1))
                row.append(v)
            rows.append(row)
        ph = ", ".join(["%s"] * (len(T["cols"]) + 1))
        cur.executemany(f"INSERT INTO {T['phys']} VALUES ({ph})", rows)
    conn.commit()
    return meta
