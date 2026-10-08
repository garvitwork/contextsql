"""Score preds_base.jsonl vs preds_finetuned.jsonl.
business rows: execution accuracy on local MySQL (result sets must match)
base rows:     normalized exact match (no database available)
Usage: python scripts\\eval_predictions.py preds_base.jsonl preds_finetuned.jsonl [--log] [--limit=N]"""
import os, sys, json, re
from functools import lru_cache
from decimal import Decimal
import pymysql
from dotenv import load_dotenv

load_dotenv()
files = [a for a in sys.argv[1:] if not a.startswith("--")]
LIMIT = int(next((a.split('=')[1] for a in sys.argv if a.startswith('--limit=')), 10**9))
assert len(files) == 2, __doc__
conn = pymysql.connect(host=os.getenv("MYSQL_HOST"), port=int(os.getenv("MYSQL_PORT")),
                       user=os.getenv("MYSQL_USER"), password=os.getenv("MYSQL_PASSWORD"),
                       database=os.getenv("MYSQL_DB"))
cur = conn.cursor()

@lru_cache(maxsize=None)
def fetch(sql):
    if not re.match(r"^\s*(select|with)\b", sql, re.I) or ";" in sql.strip().rstrip(";"):
        return None
    try:
        cur.execute("START TRANSACTION READ ONLY"); cur.execute(sql); rows = cur.fetchall()
        return rows
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
    if r["source"] == "business":
        g, p = fetch(r["gold"]), fetch(r["pred"])
        if g is None or p is None: return False
        ordered = "order by" in r["gold"].lower()
        return norm_rows(g, ordered) == norm_rows(p, ordered)
    return norm_text(r["gold"]) == norm_text(r["pred"])

def score(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")][:LIMIT]
    res = {}
    for key, flt in [("business", lambda r: r["source"] == "business"),
                     ("base", lambda r: r["source"] == "base"), ("all", lambda r: True)]:
        sub = [r for r in rows if flt(r)]
        res[key] = (100 * sum(correct(r) for r in sub) / len(sub)) if sub else float("nan")
    return res

b, f = score(files[0]), score(files[1])
print(f"{'':10}{'base model':>12}{'fine-tuned':>12}{'gain':>8}")
for k in ["business", "base", "all"]:
    print(f"{k:10}{b[k]:11.1f}%{f[k]:11.1f}%{f[k]-b[k]:+7.1f}")
gain = f["business"] - b["business"]
print("\nGOAL (+15 pts on business, unseen templates):", "PASS" if gain >= 15 else "NOT YET")
if "--log" in sys.argv:
    import dagshub, mlflow
    dagshub.init(repo_owner=os.environ["DAGSHUB_USER"], repo_name=os.environ["DAGSHUB_REPO"], mlflow=True)
    mlflow.set_experiment("contextsql-eval")
    with mlflow.start_run(run_name="test-set-eval"):
        for k in b: mlflow.log_metric(f"base_{k}_acc", b[k]); mlflow.log_metric(f"ft_{k}_acc", f[k])
        mlflow.log_metric("business_gain_pts", gain)
