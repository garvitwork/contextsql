"""Score base vs fine-tuned predictions. Execution accuracy for business + synthetic rows (each on its own database),
normalized exact match for base rows (no database available).
Usage: python scripts\\eval_predictions.py preds_v2_base.jsonl preds_v2_finetuned.jsonl [--log] [--limit=N] [--lenient]"""
import os, sys, json, re
from collections import defaultdict
from decimal import Decimal
from functools import lru_cache
import pymysql
from dotenv import load_dotenv

load_dotenv()
files = [a for a in sys.argv[1:] if not a.startswith("--")]
LENIENT = "--lenient" in sys.argv
LIMIT = int(next((a.split('=')[1] for a in sys.argv if a.startswith('--limit=')), 10**9))
assert len(files) == 2, __doc__
CONNS = {}

def cursor(db):
    if db not in CONNS:
        CONNS[db] = pymysql.connect(host=os.getenv("MYSQL_HOST"), port=int(os.getenv("MYSQL_PORT")),
                                    user=os.getenv("MYSQL_USER"), password=os.getenv("MYSQL_PASSWORD"), database=db)
    return CONNS[db].cursor()

@lru_cache(maxsize=None)
def fetch(db, sql):
    if not re.match(r"^\s*(select|with)\b", sql, re.I) or ";" in sql.strip().rstrip(";"):
        return None
    cur = cursor(db)
    try:
        cur.execute("START TRANSACTION READ ONLY"); cur.execute(sql); return cur.fetchall()
    except Exception:
        return None
    finally:
        try: cur.execute("ROLLBACK")
        except Exception: pass

def norm_rows(rows, ordered):
    out = [tuple(round(float(v), 2) if isinstance(v, (Decimal, float)) else (str(v) if v is not None else None)
                 for v in r) for r in rows]
    return out if ordered else sorted(out, key=repr)

def norm_text(s): return re.sub(r"\s+", "", s.lower()).rstrip(";")

def correct(r):
    if r["source"] in ("business", "synthetic"):
        db = r.get("db") or os.getenv("MYSQL_DB")
        g, p = fetch(db, r["gold"]), fetch(db, r["pred"])
        if g is None or p is None: return False
        ordered = "order by" in r["gold"].lower()
        if norm_rows(g, ordered) == norm_rows(p, ordered):
            return True
        if LENIENT and g and p and len(g) == len(p):      # same row count and same last-column values
            last = lambda rows: sorted(repr(round(float(r[-1]), 2)) if isinstance(r[-1], (Decimal, float, int)) else repr(r[-1]) for r in rows)
            return last(g) == last(p)
        return False
    return norm_text(r["gold"]) == norm_text(r["pred"])

def score(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")][:LIMIT]
    res, per_db = {}, defaultdict(lambda: [0, 0])
    for key in ("business", "synthetic", "base", "all"):
        sub = [r for r in rows if key == "all" or r["source"] == key]
        res[key] = (100 * sum(correct(r) for r in sub) / len(sub)) if sub else float("nan")
    for r in rows:
        if r["source"] == "synthetic":
            per_db[r["db"]][0] += correct(r); per_db[r["db"]][1] += 1
    return res, per_db

(b, bdb), (f, fdb) = score(files[0]), score(files[1])
print(f"{'':12}{'base model':>12}{'fine-tuned':>12}{'gain':>8}")
for k in ["business", "synthetic", "base", "all"]:
    print(f"{k:12}{b[k]:11.1f}%{f[k]:11.1f}%{f[k]-b[k]:+7.1f}")
print("\nper unseen database (execution accuracy):")
for db in sorted(fdb):
    fa, ft = fdb[db]; ba, bt = bdb[db]
    print(f"  {db:22} base {100*ba/bt:5.1f}%   fine-tuned {100*fa/ft:5.1f}%   ({ft} questions)")
print("\nGOAL: fine-tuned beats base by 15+ pts on unseen databases:", "PASS" if f["synthetic"] - b["synthetic"] >= 15 else "NOT YET")
if "--log" in sys.argv:
    import dagshub, mlflow
    dagshub.init(repo_owner=os.environ["DAGSHUB_USER"], repo_name=os.environ["DAGSHUB_REPO"], mlflow=True)
    mlflow.set_experiment("contextsql-eval")
    with mlflow.start_run(run_name="test-set-eval-v2"):
        for k in b: mlflow.log_metric(f"base_{k}_acc", b[k]); mlflow.log_metric(f"ft_{k}_acc", f[k])
        for db in fdb: mlflow.log_metric(f"ft_{db}_acc", 100 * fdb[db][0] / fdb[db][1])
