"""Retrieval recall when ~45 tables from 12 different companies are mixed into ONE database."""
import os, sys, random, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["CONTEXTSQL_HOME"] = "/tmp/ctxhome_scale"
from dotenv import load_dotenv; load_dotenv()
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from contextsql.learn import scan
from contextsql.retrieve import select
from synth.specs import SPECS, HELD_OUT
from synth.make_dbs import build_meta
from synth.qgen import generate

def eng(db):
    return create_engine(URL.create("mysql+pymysql", username=os.getenv("MYSQL_USER"), password=os.getenv("MYSQL_PASSWORD"),
                                    host="127.0.0.1", port=3306, database=db))
rng = random.Random(3)
metas, knows, qs = {}, {}, {}
for d in SPECS:
    metas[d] = build_meta(d); e = eng(metas[d]["db"])
    knows[d], _ = scan(e, exclude=set(), say=lambda *_: None)
    qs[d] = generate(metas[d], e, rng, per_family=6)
count = collections.Counter(t for k in knows.values() for t in k["tables"])
merged = {"tables": {}, "notes": [], "values": {}}
for d, k in knows.items():
    for t, m in k["tables"].items():
        if count[t] == 1: merged["tables"][t] = m
    merged["notes"] += [n for n in k["notes"] if count[n["table"]] == 1]
    merged["values"].update({kk: v for kk, v in k["values"].items() if count[kk.split(".")[0]] == 1})
print("tables in merged database:", len(merged["tables"]))
tot = ok = 0; sizes = []; per = {}
for d in SPECS:
    a = b = 0
    for ex in qs[d]:
        if any(count[t] > 1 for t in ex["tables"]): continue
        sel = select(ex["question"], merged, {})
        a += 1; b += set(ex["tables"]) <= set(sel["tables"]); sizes.append(len(sel["tables"]))
    per[d] = (b, a); tot += a; ok += b
for d, (b, a) in per.items():
    print(f"{d:14} recall {100*b/max(a,1):5.1f}%  ({b}/{a})" + ("  [held-out]" if d in HELD_OUT else ""))
print(f"\nOVERALL recall of needed tables: {100*ok/tot:.1f}%  | avg tables shown to model: {sum(sizes)/len(sizes):.1f}")
