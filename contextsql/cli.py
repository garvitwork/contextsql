"""contextsql connect | learn | ask | glossary | status"""
import argparse, getpass, os, sys
from pathlib import Path
from . import glossary as gl
from .config import CONFIG, KNOW, LOG, load_json, save_json
from .db import make_url, get_engine

DEFAULT_MODEL = "models/contextsql-q4_k_m.gguf"

def need(path, hint):
    obj = load_json(path)
    if obj is None:
        sys.exit(f"Not ready yet - run: {hint}")
    return obj

def cmd_connect(a):
    d = a.dialect
    if d == "sqlite":
        db = a.db or input("SQLite file path: ")
        url = make_url("sqlite", database=db)
    else:
        host = a.host or input("Host [127.0.0.1]: ") or "127.0.0.1"
        port = a.port or int(input(f"Port [{3306 if d == 'mysql' else 5432}]: ") or (3306 if d == "mysql" else 5432))
        user = a.user or input("User (a READ-ONLY user is strongly recommended): ")
        pw = a.password if a.password is not None else getpass.getpass("Password: ")
        db = a.db or input("Database name: ")
        url = make_url(d, host, port, user, pw, db)
    try:
        with get_engine(url).connect() as c:
            c.exec_driver_sql("SELECT 1")
    except Exception as e:
        sys.exit(f"Could not connect: {getattr(e, 'orig', e)}")
    model = a.model or (str(Path(DEFAULT_MODEL).resolve()) if Path(DEFAULT_MODEL).exists() else "")
    save_json(CONFIG, {"url": url, "model": model})
    print("Connected and saved." + ("" if model else "\nNo model found - pass --model path\\to\\contextsql-q4_k_m.gguf"))
    print("Next: contextsql learn")

def cmd_learn(a):
    from .learn import learn
    cfg = need(CONFIG, "contextsql connect")
    print("Learning your database (one-time) ...")
    know, imported = learn(get_engine(cfg["url"]))
    rows = sum(t.get("rows", 0) for t in know["tables"].values())
    print(f"\nDone: {len(know['tables'])} tables, {rows:,} rows scanned, {len(know['notes'])} data notes, "
          f"{len(know.get('autogloss', {}))} auto glossary terms, {imported} glossary terms imported.")
    for n in know["notes"][:6]:
        print("  -", n["text"])
    if not gl.load():
        print("\nTip: teach it your key metrics (2 minutes):\n"
              '  contextsql glossary add "revenue" "Sum of quantity*price for completed orders" '
              '"SUM(quantity*unit_price)" --tables orders,order_items')
    print("\nNext: contextsql ask \"your question\"")

def show(r):
    print(f"\nSQL ({r.attempts} attempt{'s' if r.attempts != 1 else ''}, {r.latency_ms} ms; tables: {', '.join(r.tables)}):\n  {r.sql}")
    if r.confidence == "low":
        print("  (low confidence - please check the SQL above, or rephrase / add a glossary term)")
    if not r.ok:
        print(f"\nCould not answer: {r.error}"); return
    if not r.rows:
        print("\n(no rows)"); return
    cells = [[("NULL" if v is None else str(v)) for v in row] for row in r.rows[:20]]
    w = [max(len(str(c)), *(len(row[i]) for row in cells)) for i, c in enumerate(r.columns)]
    print("\n" + "  ".join(str(c).ljust(w[i]) for i, c in enumerate(r.columns)))
    print("  ".join("-" * x for x in w))
    for row in cells: print("  ".join(v.ljust(w[i]) for i, v in enumerate(row)))
    more = len(r.rows) - 20
    print(f"\n{len(r.rows)}{'+' if r.truncated else ''} row(s)" + (f" (showing 20, {more} more)" if more > 0 else ""))

def cmd_ask(a):
    from .agent import Agent, LlamaGenerator
    cfg = need(CONFIG, "contextsql connect")
    know = need(KNOW, "contextsql learn")
    if not cfg.get("model") or not Path(cfg["model"]).exists():
        sys.exit("Model file not found. Run: contextsql connect --model path\\to\\contextsql-q4_k_m.gguf")
    print("Loading model ...")
    agent = Agent(get_engine(cfg["url"]), know, LlamaGenerator(cfg["model"], threads=a.threads))
    q = " ".join(a.question).strip()
    if q:
        show(agent.ask(q)); return
    print("Ask anything about your data (empty line to quit).")
    while True:
        q = input("\n> ").strip()
        if not q: break
        show(agent.ask(q))

def cmd_glossary(a):
    if a.action == "add":
        if not (a.term and a.definition and a.sql): sys.exit('usage: contextsql glossary add "term" "definition" "sql" [--tables a,b]')
        gl.add(a.term, a.definition, a.sql, [t for t in (a.tables or "").split(",") if t])
        print(f"Added '{a.term}'. Re-run learn is not needed.")
    elif a.action == "remove":
        print("Removed." if gl.remove(a.term) else "Not found.")
    else:
        auto = (load_json(KNOW) or {}).get("autogloss", {})
        for k, g in {**auto, **gl.load()}.items():
            tag = " (auto)" if k in auto and k not in gl.load() else ""
            print(f"- {k}{tag}: {g['definition']}\n    SQL: {g['sql']}  tables: {', '.join(g['tables'])}")

def cmd_status(a):
    cfg, know = load_json(CONFIG), load_json(KNOW)
    print("connected:", bool(cfg), "| model:", (cfg or {}).get("model") or "-")
    if know:
        print(f"learned: {len(know['tables'])} tables, {len(know['notes'])} notes, at {know['learned_at']}")
    print("glossary terms:", len(gl.load()))

def main(argv=None):
    p = argparse.ArgumentParser(prog="contextsql", description="Ask your database questions in plain language - local and free.")
    s = p.add_subparsers(dest="cmd", required=True)
    c = s.add_parser("connect"); c.set_defaults(fn=cmd_connect)
    c.add_argument("--dialect", default="mysql", choices=["mysql", "postgresql", "sqlite"])
    c.add_argument("--host"); c.add_argument("--port", type=int); c.add_argument("--user")
    c.add_argument("--password"); c.add_argument("--db"); c.add_argument("--model")
    s.add_parser("learn").set_defaults(fn=cmd_learn)
    k = s.add_parser("ask"); k.add_argument("question", nargs="*"); k.add_argument("--threads", type=int); k.set_defaults(fn=cmd_ask)
    g = s.add_parser("glossary"); g.set_defaults(fn=cmd_glossary)
    g.add_argument("action", choices=["add", "list", "remove"], nargs="?", default="list")
    g.add_argument("term", nargs="?"); g.add_argument("definition", nargs="?"); g.add_argument("sql", nargs="?")
    g.add_argument("--tables")
    s.add_parser("status").set_defaults(fn=cmd_status)
    a = p.parse_args(argv)
    a.fn(a)

if __name__ == "__main__":
    main()
