"""Local storage: everything lives in ~/.contextsql (override with CONTEXTSQL_HOME)."""
import json, os
from pathlib import Path

HOME = Path(os.getenv("CONTEXTSQL_HOME", Path.home() / ".contextsql"))
CONFIG, KNOW, GLOSS, LOG = (HOME / "config.json", HOME / "knowledge.json",
                            HOME / "glossary.json", HOME / "query_log.jsonl")

def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default

def save_json(path, obj):
    HOME.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
