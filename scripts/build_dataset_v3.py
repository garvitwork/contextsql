"""v3 dataset = v1 (retail + base) + 50 synthetic company databases (38 train / 12 fully held-out)
with auto-glossary questions, 'extra columns' requests, paraphrases and light typos.
Run:  python scripts\\build_dataset_v3.py --smoke   (2 databases, quick check)   then without --smoke."""
import os, sys, json, random, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from contextsql.learn import scan
from contextsql.prompt import build_prompt
from contextsql import autoglossary as ag
from contextsql.phrasing import paraphrase, typo
from synth.specs import DB_KEYS, HELD_OUT
from synth.make_dbs import build_meta
from synth.qgen import generate

load_dotenv()
ap = argparse.ArgumentParser()
ap.add_argument("--per-family", type=int, default=6)
ap.add_argument("--auto-per-db", type=int, default=40)
ap.add_argument("--styles", type=int, default=2)
ap.add_argument("--max-train", type=int, default=9000)
ap.add_argument("--src", default="data/processed")
ap.add_argument("--out", default="data/processed_v3")
ap.add_argument("--smoke", action="store_true")
ap.add_argument("--log", action="store_true")
args = ap.parse_args()
rng = random.Random(23)

def _lc(q): return q[0].lower() + q[1:]
STYLES = [lambda q: q, lambda q: q.rstrip("?."), lambda q: "Please " + _lc(q).rstrip("?.") + ".",
          lambda q: "Can you show me: " + _lc(q), lambda q: "I want to know: " + _lc(q),
          lambda q: q.lower().rstrip("?."), lambda q: "Hey, " + _lc(q), lambda q: "Quick question - " + _lc(q)]

def engine_for(db):
    return create_engine(URL.create("mysql+pymysql", username=os.getenv("MYSQL_USER"), password=os.getenv("MYSQL_PASSWORD"),
                                    host=os.getenv("MYSQL_HOST", "127.0.0.1"), port=int(os.getenv("MYSQL_PORT", 3306)), database=db))

def verify(eng, items, cap):
    rng.shuffle(items); out = []
    with eng.connect() as c:
        for it in items:
            if len(out) >= cap: break
            try:
                rows = c.exec_driver_sql(it["sql"].replace("%", "%%")).fetchall()
            except Exception:
                continue
            if not rows or all(v is None for v in rows[0]): continue
            out.append(dict(it, question=rng.choice(it["variants"])))
    return out

train, val, test = [], [], []
keys = ["hr", "hotel"] if args.smoke else DB_KEYS
for key in keys:
    try:
        meta = build_meta(key); db = meta["db"]; eng = engine_for(db)
        know, _ = scan(eng, exclude=set(), say=lambda *_: None)
        L = ag.Labels(meta)
        entries = ag.build(know, L)
        gmap = {t: {"definition": e["definition"], "sql": e["sql"]} for t, e in entries.items()}
        exs = generate(meta, eng, rng, per_family=args.per_family)
        exs += verify(eng, ag.examples(know, L, entries), args.auto_per_db)
        all_tables, n_done = list(know["tables"]), 0
        for ex in exs:
            tabs = list(dict.fromkeys(ex["tables"]))
            extra = [t for t in all_tables if t not in tabs]
            if extra and rng.random() < 0.5:
                tabs += rng.sample(extra, min(len(extra), rng.randint(1, 2)))
            tabs.sort(key=all_tables.index)
            schema = "\n\n".join(know["tables"][t]["ddl"] for t in tabs)
            ctx = []
            for n in know["notes"]:
                if n["table"] not in tabs: continue
                if n["kind"] == "join":
                    if n["ref_table"] in tabs: ctx.append(f"- data note: {n['text']}")
                elif n["kind"] in ("variants", "null") or f"{n['table']}.{n['column']}" in ex["used"]:
                    ctx.append(f"- data note: {n['text']}")
            terms = [t for t in ex.get("terms", []) if t in gmap]
            for t in list(terms):                                   # pull in terms the definition depends on
                d = gmap[t]["definition"].lower()
                terms += [o for o in gmap if o not in terms and o in d]
            spare = [g for g in gmap if g not in terms]
            if spare and rng.random() < 0.5:
                terms += rng.sample(spare, min(len(spare), rng.randint(1, 2)))
            ctx += [f"- {k}: {gmap[k]['definition']} SQL: {gmap[k]['sql']}" for k in terms]
            if ex.get("req"): ctx.append(f"- requested columns: {', '.join(ex['req'])}")
            rng.shuffle(ctx)
            sql = " ".join(ex["sql"].split()).rstrip(";") + ";"
            for st in rng.sample(STYLES, args.styles):
                q = typo(st(paraphrase(ex["question"], rng, ex.get("extra", False))), rng)
                row = dict(prompt=build_prompt(schema, ctx, q), completion=sql, source="synthetic",
                           template=ex["family"], db=db, held_out=key in HELD_OUT)
                (test if key in HELD_OUT else (val if rng.random() < 0.1 else train)).append(row)
                n_done += 1
        print(f"{db:28} {len(exs):4} questions -> {n_done:4} examples ({len(entries)} glossary terms)" + ("  [HELD OUT]" if key in HELD_OUT else ""), flush=True)
    except Exception as e:
        print(f"SKIPPED {key}: {type(e).__name__}: {e}", flush=True)

mydb = os.getenv("MYSQL_DB", "contextsql")
for name, bucket in [("train", train), ("val", val), ("test", test)]:
    for l in open(f"{args.src}/{name}.jsonl", encoding="utf-8"):
        r = json.loads(l); r["db"] = mydb if r["source"] == "business" else None
        bucket.append(r)
if len(train) > args.max_train:                                    # keep every retail business row, trim the rest
    keep = [r for r in train if r["source"] == "business"]
    rest = [r for r in train if r["source"] != "business"]
    rng.shuffle(rest); train = keep + rest[: max(0, args.max_train - len(keep))]
    print(f"train capped at {len(train)} rows (--max-train)")
for b in (train, val, test): rng.shuffle(b)
os.makedirs(args.out, exist_ok=True)
for name, b in [("train", train), ("val", val), ("test", test)]:
    with open(f"{args.out}/{name}.jsonl", "w", encoding="utf-8") as f:
        for r in b: f.write(json.dumps(r, ensure_ascii=False) + "\n")
tot = {"train": len(train), "val": len(val), "test": len(test)}
by = {k: sum(1 for r in test if r["source"] == k) for k in ("business", "base", "synthetic")}
print("\nsizes:", tot, "| test by source:", by)
if args.log:
    import dagshub, mlflow
    dagshub.init(repo_owner=os.environ["DAGSHUB_USER"], repo_name=os.environ["DAGSHUB_REPO"], mlflow=True)
    mlflow.set_experiment("contextsql-dataset")
    with mlflow.start_run(run_name="build_dataset_v3"):
        mlflow.log_params({"per_family": args.per_family, "auto_per_db": args.auto_per_db, "styles": args.styles,
                           "databases": len(keys), "held_out": len(HELD_OUT)})
        mlflow.log_metrics({**tot, **{f"test_{k}": v for k, v in by.items()}})
