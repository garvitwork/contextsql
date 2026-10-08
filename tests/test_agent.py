import os, sys, json, sqlite3, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["CONTEXTSQL_HOME"] = "/tmp/ctxhome"
from contextsql.config import CONFIG, KNOW, load_json
from contextsql.db import get_engine
from contextsql.agent import Agent, validate
from contextsql.retrieve import select
from contextsql import glossary as gl

class Mock:
    """Stand-in for the LLM: returns scripted SQL per call, records prompts."""
    def __init__(self, outputs): self.outputs, self.prompts = list(outputs), []
    def generate(self, prompt, temperature=0.0):
        self.prompts.append(prompt); return self.outputs.pop(0)

cfg, know = load_json(CONFIG), load_json(KNOW)
eng = get_engine(cfg["url"])
print("status notes:", [n["text"] for n in know["notes"] if n["column"] == "status"])

print("\n--- retrieval ---")
for q in ["What is our total revenue?", "Top 5 customers by revenue", "How many customers are in India?",
          "Which payment method brings the most money?", "How many unpaid orders?", "Average order value by country"]:
    s = select(q, know, gl.load())
    print(f"{q:48} tables={s['tables']} gloss={s['glossary']} notes={[n['column'] for n in s['notes']]}")

print("\n--- agent: normal + % in SQL ---")
m = Mock(["SELECT DATE_FORMAT(o.order_date,'%Y-%m') AS month, COUNT(*) AS n FROM orders o GROUP BY month ORDER BY month LIMIT 3;"])
r = Agent(eng, know, m).ask("Orders per month")
print(r.ok, r.attempts, r.columns, r.rows)

print("\n--- agent: self-correction (bad column first) ---")
m = Mock(["SELECT COUNT(*) FROM customers WHERE nation = 'India';",
          "SELECT COUNT(*) AS customers FROM customers WHERE country = 'India';"])
r = Agent(eng, know, m).ask("How many customers are in India?")
print(r.ok, "attempts:", r.attempts, r.rows, "| retry prompt has hint:", "previous attempt failed" in m.prompts[1])

print("\n--- safety ---")
for s in ["DELETE FROM orders;", "SELECT 1; DROP TABLE orders;", "SELECT * FROM orders WHERE status = 'update';",
          "WITH t AS (SELECT 1) SELECT * FROM t;", "SELECT * INTO OUTFILE '/tmp/x' FROM orders;"]:
    print(f"{s[:55]:58}", validate(s))
m = Mock(["DROP TABLE orders;"] * 3)
r = Agent(eng, know, m).ask("remove everything")
print("destructive ->", r.ok, r.error)

print("\n--- prompt for revenue question ---")
m = Mock(["SELECT 1;"]); Agent(eng, know, m).ask("Top 5 customers by revenue")
print(m.prompts[0][-1500:])

print("\n--- SQLite universality ---")
tmp = tempfile.mkdtemp(); path = os.path.join(tmp, "t.db")
c = sqlite3.connect(path)
c.executescript("""CREATE TABLE dept(id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE emp(id INTEGER PRIMARY KEY, name TEXT, dept_id INTEGER REFERENCES dept(id), salary REAL, level TEXT);
INSERT INTO dept VALUES (1,'Sales'),(2,'Eng');
INSERT INTO emp VALUES (1,'A',1,100,'Senior'),(2,'B',2,200,'senior'),(3,'C',2,150,'Junior'),(4,'D',1,NULL,'Junior');""")
c.commit(); c.close()
import contextsql.learn as L
from pathlib import Path
L.KNOW = Path(tmp) / 'k.json'   # keep the MySQL knowledge file untouched
from contextsql.learn import learn
e2 = get_engine(f"sqlite:///{path}")
k2, _ = learn(e2, say=lambda *_: None)
print([n["text"] for n in k2["notes"]])
r = Agent(e2, k2, Mock(["SELECT d.name, AVG(e.salary) AS avg_salary FROM emp e JOIN dept d ON d.id = e.dept_id GROUP BY d.name;"])).ask("average salary by department")
print(r.ok, r.rows, r.tables)
