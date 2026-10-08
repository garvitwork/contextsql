"""v2 dataset = v1 (retail + base) + schema-driven examples from 12 synthetic company databases.
Three databases (hotel, manufacturing, gym) are held out entirely for testing cross-schema generalization."""
import os, sys, json, random, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from contextsql.learn import scan
from contextsql.prompt import build_prompt
from synth.specs import SPECS, HELD_OUT, DB_PREFIX
from synth.make_dbs import build_meta
from synth.qgen import generate

load_dotenv()
ap = argparse.ArgumentParser()
ap.add_argument("--per-family", type=int, default=10)
ap.add_argument("--styles", type=int, default=2)
ap.add_argument("--src", default="data/processed")
ap.add_argument("--out", default="data/processed_v2")
ap.add_argument("--log", action="store_true")
args = ap.parse_args()
rng = random.Random(11)

def _lc(q): return q[0].lower() + q[1:]
STYLES = [lambda q: q, lambda q: q.rstrip("?."), lambda q: "Please " + _lc(q).rstrip("?.") + ".",
          lambda q: "Can you show me: " + _lc(q), lambda q: "I want to know: " + _lc(q),
          lambda q: q.lower().rstrip("?."), lambda q: "Hey, " + _lc(q), lambda q: "Quick question - " + _lc(q)]

def engine_for(db):
    return create_engine(URL.create("mysql+pymysql", username=os.getenv("MYSQL_USER"), password=os.getenv("MYSQL_PASSWORD"),
                                    host=os.getenv("MYSQL_HOST", "127.0.0.1"), port=int(os.getenv("MYSQL_PORT", 3306)), database=db))

train, val, test, stats = [], [], [], {}
for domain in SPECS:
    meta = build_meta(domain); db = meta["db"]; eng = engine_for(db)
    know, _ = scan(eng, exclude=set(), say=lambda *_: None)
    exs = generate(meta, eng, rng, per_family=args.per_family)
    all_tables = list(know["tables"])
    n_done = 0
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
        rng.shuffle(ctx)
        sql = " ".join(ex["sql"].split()) + ";"
        for st in rng.sample(STYLES, args.styles):
            row = dict(prompt=build_prompt(schema, ctx, st(ex["question"])), completion=sql, source="synthetic",
                       template=ex["family"], db=db, held_out=domain in HELD_OUT)
            (test if domain in HELD_OUT else (val if rng.random() < 0.1 else train)).append(row)
            n_done += 1
    stats[db] = n_done
    print(f"{db:22} {len(exs):4} questions -> {n_done:4} examples" + ("  [HELD OUT]" if domain in HELD_OUT else ""))

mydb = os.getenv("MYSQL_DB", "contextsql")
for name, bucket in [("train", train), ("val", val), ("test", test)]:
    for l in open(f"{args.src}/{name}.jsonl", encoding="utf-8"):
        r = json.loads(l); r["db"] = mydb if r["source"] == "business" else None
        bucket.append(r)
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
    with mlflow.start_run(run_name="build_dataset_v2"):
        mlflow.log_params({"per_family": args.per_family, "styles": args.styles, "held_out": ",".join(sorted(HELD_OUT))})
        mlflow.log_metrics({**tot, **{f"test_{k}": v for k, v in by.items()}})
