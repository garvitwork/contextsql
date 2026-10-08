"""Question -> SQL (local LLM) -> validate -> run read-only -> self-correct on errors."""
import re, time, json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from . import glossary as gl
from .config import LOG, HOME
from .prompt import build_prompt
from .retrieve import select

MAX_PROMPT_TOKENS, MAX_ROWS = 800, 200
FORBID = re.compile(r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|replace|merge|call|exec|"
                    r"outfile|dumpfile|load_file|sleep|benchmark|pg_sleep)\b", re.I)

class LlamaGenerator:
    def __init__(self, path, n_ctx=2048, threads=None):
        try:
            from llama_cpp import Llama
        except ImportError:
            raise SystemExit("llama-cpp-python is not installed. Run:\n  pip install llama-cpp-python "
                             "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu")
        self.llm = Llama(model_path=path, n_ctx=n_ctx, n_threads=threads, verbose=False)

    def count_tokens(self, text):
        return len(self.llm.tokenize(text.encode("utf-8"), add_bos=False))

    def generate(self, prompt, temperature=0.0):
        out = self.llm(prompt, max_tokens=300, temperature=temperature, stop=[";"], echo=False)
        return out["choices"][0]["text"]

def prune_ddl(meta, keep, max_cols=25):
    """Show only relevant columns of very wide tables (keeps keys, matched columns and the first few)."""
    if not keep or len(meta["columns"]) <= max_cols:
        return meta["ddl"]
    lines = meta["ddl"].split("\n")
    head, body, tail = lines[0], lines[1:-1], lines[-1]
    out = [l for l in body if l.strip().split(" ")[0].rstrip(",") in keep or
           l.strip().startswith(("PRIMARY", "CONSTRAINT", "FOREIGN"))]
    out = [l.rstrip(",") for l in out]
    return head + "\n" + ",\n".join(out) + "\n" + tail

def clean_sql(text):
    text = re.sub(r"```(?:sql)?", "", text).strip()
    return " ".join(text.split()).rstrip(";").strip() + ";"

def validate(sql):
    s = re.sub(r"--[^\n]*|/\*.*?\*/", "", sql, flags=re.S).strip().rstrip(";")
    s = re.sub(r"'(?:[^']|'')*'", "''", s)          # ignore words inside string literals
    if ";" in s: return False, "only one statement is allowed"
    if not re.match(r"^\s*(select|with)\b", s, re.I): return False, "only SELECT queries are allowed"
    m = FORBID.search(s)
    if m: return False, f"forbidden keyword: {m.group(0)}"
    return True, ""

@dataclass
class Result:
    question: str
    sql: str = ""
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    ok: bool = False
    error: str = ""
    attempts: int = 0
    latency_ms: int = 0
    tables: list = field(default_factory=list)
    truncated: bool = False

class Agent:
    def __init__(self, engine, know, generator, max_attempts=3):
        self.engine, self.know, self.gen, self.max_attempts = engine, know, generator, max_attempts

    def _count(self, text):
        return self.gen.count_tokens(text) if hasattr(self.gen, "count_tokens") else len(text) // 3

    def make_prompt(self, question, hint=None):
        gloss = gl.load()
        sel = select(question, self.know, gloss)
        tables, notes, terms = list(sel["tables"]), list(sel["notes"]), list(sel["glossary"])
        while True:
            ctx = [f"- {k}: {gloss[k]['definition']} SQL: {gloss[k]['sql']}" for k in terms]
            ctx += [f"- data note: {n['text']}" for n in notes if n["table"] in tables
                    and (n["kind"] != "join" or n["ref_table"] in tables)]
            if hint: ctx.append(f"- note: {hint}")
            schema = "\n\n".join(prune_ddl(self.know["tables"][t], sel["keep"].get(t)) for t in tables)
            prompt = build_prompt(schema, ctx, question)
            if self._count(prompt) <= MAX_PROMPT_TOKENS: break
            if len([n for n in notes if n["table"] in tables and n["kind"] == "values"]):
                notes = [n for n in notes if n["kind"] != "values"]       # drop value lists first
            elif len(tables) > 1:
                tables.remove(min(tables, key=lambda t: sel["scores"].get(t, 0)))
            else:
                break
        return prompt, tables

    def run_sql(self, sql):
        d = self.engine.dialect.name
        body = sql.rstrip(";")
        if d in ("mysql", "postgresql"): body = body.replace("%", "%%")
        with self.engine.connect() as c:
            try:
                if d == "mysql": c.exec_driver_sql("SET SESSION TRANSACTION READ ONLY")
                elif d == "postgresql": c.exec_driver_sql("SET TRANSACTION READ ONLY")
            except Exception:
                pass
            c.exec_driver_sql(("EXPLAIN QUERY PLAN " if d == "sqlite" else "EXPLAIN ") + body)
            res = c.exec_driver_sql(body)
            cols = list(res.keys()); rows = res.fetchmany(MAX_ROWS + 1)
        return cols, [tuple(r) for r in rows[:MAX_ROWS]], len(rows) > MAX_ROWS

    def ask(self, question):
        t0, r, hint = time.time(), Result(question=question), None
        for i in range(1, self.max_attempts + 1):
            prompt, tables = self.make_prompt(question, hint)
            sql = clean_sql(self.gen.generate(prompt, temperature=0.0 if i == 1 else 0.2 * (i - 1)))
            r.sql, r.tables, r.attempts = sql, tables, i
            ok, err = validate(sql)
            if ok:
                try:
                    r.columns, r.rows, r.truncated = self.run_sql(sql)
                    r.ok, r.error = True, ""
                    break
                except Exception as e:
                    err = str(getattr(e, "orig", e))[:300]
            r.error = err
            hint = f"the previous attempt failed ({err}). Previous SQL: {sql} Write a corrected query."
        r.latency_ms = int((time.time() - t0) * 1000)
        try:
            HOME.mkdir(parents=True, exist_ok=True)
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                    "question": question, "sql": r.sql, "ok": r.ok, "error": r.error,
                                    "attempts": r.attempts, "latency_ms": r.latency_ms}) + "\n")
        except Exception:
            pass
        return r
