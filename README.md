# ContextSQL
Business-context-aware text-to-SQL agent. MySQL + fine-tuned LLM + DagHub MLOps. FastAPI backend (frontend later).

## Day 1 setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill DAGSHUB_USER

docker compose up -d            # MySQL on :3307, schema + glossary auto-loaded
python scripts/seed_data.py
python scripts/check_db.py

# DagHub + DVC
git init && dvc init
dagshub login                   # or: dagshub.init handles auth in browser
dvc remote add origin https://dagshub.com/<user>/contextsql.dvc
dvc remote default origin
python scripts/init_dagshub.py

python scripts/fetch_base_data.py
dvc add data/raw/sql_create_context.jsonl
git add . && git commit -m "day1: mysql, seed, dvc base data"
git remote add origin https://dagshub.com/<user>/contextsql.git
git push -u origin main && dvc push
```

## Day 1 done when
- `check_db.py` shows 500/60/5000 rows and messy statuses
- MLflow smoke-test run visible on DagHub
- base dataset tracked by DVC and pushed
