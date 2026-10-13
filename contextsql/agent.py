"""Question -> SQL (local LLM) -> validate -> run read-only -> self-correct on errors."""
import os, re, time, json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from . import feedback, glossary as gl
from .config import LOG, HOME
from .hints import FAIL, EMPTY, MISS
from .phrasing import requested_columns
from .prompt import build_prompt
from .retrieve import select

MAX_PROMPT_TOKENS, MAX_ROWS, TIMEOUT_S = 1000, 200, 15
FORBID = re.compile(r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|replace|merge|call|exec|"
                    r"outfile|dumpfile|load_file|sleep|benchmark|pg_sleep)\b", re.I)

class LlamaGenerator:
    def __init__(self, path, n_ctx=2048, threads=None):
        try:
            from llama_cpp import Llama
        except ImportError:
            raise SystemExit("llama-cpp-python is not installed. Run:\n  pip install llama-cpp-python "
                             "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu")
        threads = threads or max(1, (os.cpu_count() or 2) // 2)
        self.llm = Llama(model_path=path, n_ctx=n_ctx, n_threads=8, n_batch=256, verbose=False)
        try:                                   # reuse the processed prompt prefix between questions
            from llama_cpp.llama_cache import LlamaRAMCache
            self.llm.set_cache(LlamaRAMCache(capacity_bytes=256 << 20))
        except Exception:
            pass

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
    confidence: str = "high"      # "low": weak table match, retries needed, or still missing requested columns

class Agent:
    def __init__(self, engine, know, generator, max_attempts=3):
        self.engine, self.know, self.gen, self.max_attempts = engine, know, generator, max_attempts
        self._cache = {}

    def _count(self, text):
        return self.gen.count_tokens(text) if hasattr(self.gen, "count_tokens") else len(text) // 3

    def glossary(self):
        return {**self.know.get("autogloss", {}), **gl.load()}     # your own entries override automatic ones

    def make_prompt(self, question, hint=None):
        gloss = self.glossary()
        sel = select(question, self.know, gloss)
        tables, notes, terms = list(sel["tables"]), list(sel["notes"]), list(sel["glossary"])
        req = requested_columns(question, self.know, tables)
        low = max(sel["scores"].values(), default=0) <= 0
        shots = feedback.similar(question, tables)
        while True:
            ctx = [f"- {k}: {gloss[k]['definition']} SQL: {gloss[k]['sql']}" for k in terms]
            ctx += [f"- data note: {n['text']}" for n in notes if n["table"] in tables
                    and (n["kind"] != "join" or n["ref_table"] in tables)]
            if req: ctx.append(f"- requested columns: {', '.join(req)}")
            ctx += [f"- example: Q: {q} SQL: {sq}" for q, sq in shots]
            if hint: ctx.append(f"- note: {hint}")
            schema = "\n\n".join(prune_ddl(self.know["tables"][t], sel["keep"].get(t)) for t in tables)
            prompt = build_prompt(schema, ctx, question)
            if self._count(prompt) <= MAX_PROMPT_TOKENS: break
            if shots:
                shots = []                                                  # drop examples first
            elif any(n["kind"] == "values" for n in notes):
                notes = [n for n in notes if n["kind"] != "values"]       # drop value lists first
            elif len(tables) > 1:
                tables.remove(min(tables, key=lambda t: sel["scores"].get(t, 0)))
            else:
                break
        return prompt, tables, low, req

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
            for stmt in (f"SET SESSION MAX_EXECUTION_TIME={TIMEOUT_S * 1000}", f"SET SESSION max_statement_time={TIMEOUT_S}",
                         f"SET statement_timeout = {TIMEOUT_S * 1000}"):
                try:
                    c.exec_driver_sql(stmt); break
                except Exception:
                    continue
            c.exec_driver_sql(("EXPLAIN QUERY PLAN " if d == "sqlite" else "EXPLAIN ") + body)
            res = c.exec_driver_sql(body)
            cols = list(res.keys()); rows = res.fetchmany(MAX_ROWS + 1)
        return cols, [tuple(r) for r in rows[:MAX_ROWS]], len(rows) > MAX_ROWS

    @staticmethod
    def missing(req, sql):
        m = re.search(r"select\s+(.*?)\s+from\b", sql, re.I | re.S)
        clause = (m.group(1) if m else sql).lower()
        return [c for c in req if c.lower() not in clause]

    def ask(self, question):
        key = " ".join(question.lower().split())
        if key in self._cache:
            return self._cache[key]
        t0, r, hint, best, low0 = time.time(), Result(question=question), None, None, False
        for i in range(1, self.max_attempts + 1):
            prompt, tables, low, req = self.make_prompt(question, hint)
            low0 = low0 or (i == 1 and low)
            raw = self.gen.generate(prompt, temperature=0.0 if i == 1 else 0.2 * (i - 1))
            r.tables, r.attempts = tables, i
            if raw.strip().lower().startswith("-- unanswerable"):          # the model says the data cannot answer this
                r.ok, r.sql, r.confidence = False, "", "low"
                r.error = raw.strip().split(":", 1)[-1].strip() or "this database has no matching information"
                best = None
                break
            sql = clean_sql(raw)
            r.sql = sql
            ok, err = validate(sql)
            if ok:
                try:
                    cols, rows, trunc = self.run_sql(sql)
                    r.columns, r.rows, r.truncated, r.ok, r.error = cols, rows, trunc, True, ""
                    miss = self.missing(req, sql)
                    if best is None or rows or not best[2]:
                        best = (sql, cols, rows, trunc, tables, i)
                    if i < self.max_attempts and (not rows or miss):
                        hint = EMPTY.format(sql=sql) if not rows else MISS.format(cols=", ".join(miss), sql=sql)
                        r.ok = False
                        continue
                    r.confidence = "low" if (low0 or i > 1 or miss or not rows) else "high"
                    break
                except Exception as e:
                    err = str(getattr(e, "orig", e))[:300]
            r.error = err
            hint = FAIL.format(err=err, sql=sql)
        if not r.ok and best:      # retries failed: fall back to the earlier valid answer
            r.sql, r.columns, r.rows, r.truncated, r.tables, r.attempts = best
            r.ok, r.error, r.confidence = True, "", "low"
        if not r.ok:
            r.confidence = "low"
        r.latency_ms = int((time.time() - t0) * 1000)
        try:
            HOME.mkdir(parents=True, exist_ok=True)
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                    "question": question, "sql": r.sql, "ok": r.ok, "error": r.error,
                                    "attempts": r.attempts, "latency_ms": r.latency_ms, "confidence": r.confidence, "tables": r.tables}) + "\n")
        except Exception:
            pass
        if r.ok:
            self._cache[key] = r
        return r
