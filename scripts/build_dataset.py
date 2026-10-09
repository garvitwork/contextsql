"""Build train/val/test jsonl: schema-diverse base data + execution-verified business examples."""
import os, sys, json, random, re, itertools, string, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymysql
from dotenv import load_dotenv
from src.sql_templates import TEMPLATES, NOTES
from contextsql.phrasing import paraphrase, typo

load_dotenv()
ap = argparse.ArgumentParser()
ap.add_argument("--base-n", type=int, default=1500)
ap.add_argument("--max-per-template", type=int, default=36)
ap.add_argument("--styles", type=int, default=4)
ap.add_argument("--log", action="store_true", help="log stats to DagHub MLflow")
args = ap.parse_args()
rng = random.Random(42)

conn = pymysql.connect(host=os.getenv("MYSQL_HOST"), port=int(os.getenv("MYSQL_PORT")),
                       user=os.getenv("MYSQL_USER"), password=os.getenv("MYSQL_PASSWORD"),
                       database=os.getenv("MYSQL_DB"))
cur = conn.cursor()

BIZ_TABLES = ["customers", "products", "orders", "order_items", "payments"]

def clean_schema(name):
    cur.execute(f"SHOW CREATE TABLE {name}")
    raw = cur.fetchone()[1].replace("`", "")
    lines = raw.split("\n")
    head, body = lines[0], [l.strip().rstrip(",") for l in lines[1:-1]]
    body = [l for l in body if not l.startswith("KEY ") and not l.startswith("UNIQUE KEY")]
    body = [re.sub(r"\s+(CHARACTER SET \w+|COLLATE \w+)", "", l) for l in body]
    body = [re.sub(r"\s+DEFAULT NULL", "", l) for l in body]
    return head + "\n  " + ",\n  ".join(body) + "\n);"

SCHEMAS = {t: clean_schema(t) for t in BIZ_TABLES}
cur.execute("SELECT term, definition, sql_snippet FROM business_glossary")
GLOSS = {r[0]: {"definition": r[1], "sql_snippet": r[2]} for r in cur.fetchall()}
cur.execute("SELECT DISTINCT country FROM customers"); COUNTRIES = sorted(r[0] for r in cur.fetchall() if r[0])
cur.execute("SELECT DISTINCT category FROM products"); CATEGORIES = sorted(r[0] for r in cur.fetchall())
cur.execute("SELECT DISTINCT segment FROM customers"); SEGMENTS = sorted(r[0] for r in cur.fetchall() if r[0])
SLOTS = {"n": [3, 5, 10], "days": [7, 30, 60, 90, 180, 365],
         "country": COUNTRIES, "category": CATEGORIES, "segment": SEGMENTS}
try: cur.execute("SET SESSION MAX_EXECUTION_TIME=5000")
except Exception: pass


def _lc(q): return q[0].lower() + q[1:]
STYLES = [
    lambda q: q,
    lambda q: q.rstrip("?."),
    lambda q: "Please " + _lc(q).rstrip("?.") + ".",
    lambda q: "Can you show me: " + _lc(q),
    lambda q: "I want to know: " + _lc(q),
    lambda q: q.lower().rstrip("?."),
    lambda q: "Hey, " + _lc(q),
    lambda q: "Quick question - " + _lc(q),
]

def norm_sql(s): return " ".join(s.split()).rstrip(";") + ";"

def prompt(schema, ctx_lines, question):
    ctx = "\n".join(ctx_lines) if ctx_lines else "(none)"
    return f"### Schema\n{schema}\n\n### Business context\n{ctx}\n\n### Question\n{question}\n\n### SQL\n"

def runs_ok(sql):
    try:
        cur.execute(sql); rows = cur.fetchall()
        return bool(rows) and not all(v is None for v in rows[0])
    except Exception:
        return False

def slot_names(t):
    names = set()
    for s in t["questions"] + [t["sql"]]:
        names |= {f for _, f, _, _ in string.Formatter().parse(s) if f}
    return sorted(names)

business, dropped = [], 0
for idx, t in enumerate(TEMPLATES):
    names = slot_names(t)
    combos = [dict(zip(names, c)) for c in itertools.product(*[SLOTS[n] for n in names])] if names else [{}]
    rng.shuffle(combos); combos = combos[:args.max_per_template]
    if not names: combos = [{} for _ in t["questions"]]
    for i, slots in enumerate(combos):
        q0 = t["questions"][i % len(t["questions"])].format(**slots)
        sql = norm_sql(t["sql"].format(**slots))
        if not runs_ok(sql): dropped += 1; continue
        for st in rng.sample(STYLES, args.styles):
          q = typo(st(paraphrase(q0, rng, bool(t.get('req')))), rng)
          tabs = list(t["tables"]); extra = [x for x in BIZ_TABLES if x not in tabs]
          if extra and rng.random() < 0.4: tabs.append(rng.choice(extra))
          tabs.sort(key=BIZ_TABLES.index)
          schema = "\n\n".join(SCHEMAS[x] for x in tabs)
          ctx = [f"- {k}: {GLOSS[k]['definition']} SQL: {GLOSS[k]['sql_snippet']}" for k in t["terms"]]
          ctx += [f"- data note: {NOTES[k]}" for k in t["notes"]]
          for k in rng.sample([g for g in GLOSS if g not in t["terms"]], rng.randint(0, 2)):
              ctx.append(f"- {k}: {GLOSS[k]['definition']} SQL: {GLOSS[k]['sql_snippet']}")
          if t.get('req'): ctx.append('- requested columns: ' + ', '.join(t['req']))
          rng.shuffle(ctx)
          business.append(dict(prompt=prompt(schema, ctx, q), completion=sql, source="business",
                               template=t["id"], held_out=(idx % 5 == 0)))

# dedupe by question text within template
seen, uniq = set(), []
for r in business:
    k = (r["template"], r["prompt"].split("### Question\n")[1])
    if k not in seen: seen.add(k); uniq.append(r)
business = uniq

base = []
bp = "data/raw/sql_create_context.jsonl"
if os.path.exists(bp):
    rows = [json.loads(l) for l in open(bp, encoding="utf-8")]
    rows = [r for r in rows if len(r["schema"]) < 1500 and len(r["sql"]) < 400]
    for r in rng.sample(rows, min(args.base_n, len(rows))):
        base.append(dict(prompt=prompt(r["schema"], [], r["question"]), completion=norm_sql(r["sql"]),
                         source="base", template="base", held_out=False))
else:
    print(f"WARNING: {bp} not found, building business-only dataset")

train, val, test = [], [], []
for r in business:
    if r["held_out"]: test.append(r)
    else: (val if rng.random() < 0.1 else train).append(r)
for r in base:
    x = rng.random()
    (test if x < 0.05 else val if x < 0.10 else train).append(r)
for s in (train, val, test): rng.shuffle(s)

os.makedirs("data/processed", exist_ok=True)
for name, s in [("train", train), ("val", val), ("test", test)]:
    with open(f"data/processed/{name}.jsonl", "w", encoding="utf-8") as f:
        for r in s: f.write(json.dumps(r, ensure_ascii=False) + "\n")

stats = dict(business=len(business), base=len(base), train=len(train), val=len(val), test=len(test),
             dropped_non_executing=dropped, templates=len(TEMPLATES),
             held_out_templates=sum(1 for i in range(len(TEMPLATES)) if i % 5 == 0))
print(json.dumps(stats, indent=2))
if args.log:
    import dagshub, mlflow
    dagshub.init(repo_owner=os.environ["DAGSHUB_USER"], repo_name=os.environ["DAGSHUB_REPO"], mlflow=True)
    mlflow.set_experiment("contextsql-dataset")
    with mlflow.start_run(run_name="build_dataset_v1"):
        mlflow.log_params({"base_n": args.base_n, "max_per_template": args.max_per_template})
        mlflow.log_metrics({k: v for k, v in stats.items()})
