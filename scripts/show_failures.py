"""List wrong predictions so we can see WHY. Usage: python scripts\\show_failures.py preds_v2_finetuned.jsonl [db] [max]"""
import os, sys, json, re
from collections import Counter
sys.argv_backup = sys.argv
path = sys.argv[1]; only = sys.argv[2] if len(sys.argv) > 2 else None; mx = int(sys.argv[3]) if len(sys.argv) > 3 else 12
sys.argv = [sys.argv[0], path, path]              # reuse the scorer's execution comparison
import importlib.util
spec = importlib.util.spec_from_file_location("ev", os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_predictions.py"))
src = open(spec.origin, encoding="utf-8").read().split("(b, bdb), (f, fdb) = score")[0]
ns = {"__name__": "ev"}; exec(compile(src, "ev", "exec"), ns)
rows = [json.loads(l) for l in open(path, encoding="utf-8")]
bad = [r for r in rows if r["source"] == "synthetic" and (only is None or r["db"] == only) and not ns["correct"](r)]
print(f"{len(bad)} wrong" + (f" in {only}" if only else ""))
print("by question type:", dict(Counter(r["template"] for r in bad).most_common()))
for r in bad[:mx]:
    print(f"\n[{r['db']} / {r['template']}]\n  gold: {r['gold']}\n  pred: {r['pred']}")
