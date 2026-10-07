"""Download the public text-to-SQL base dataset (question + CREATE TABLE context + SQL)."""
import json
from datasets import load_dataset

ds = load_dataset("b-mc2/sql-create-context", split="train")
out = "data/raw/sql_create_context.jsonl"
with open(out, "w") as f:
    for r in ds:
        f.write(json.dumps({"question": r["question"], "schema": r["context"], "sql": r["answer"]}) + "\n")
print(f"Saved {len(ds)} rows to {out}")
