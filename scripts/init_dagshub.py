"""Connect this repo to DagHub (git + DVC remote + MLflow tracking)."""
import os, dagshub, mlflow
from dotenv import load_dotenv
load_dotenv()
dagshub.init(repo_owner=os.environ["DAGSHUB_USER"], repo_name=os.environ["DAGSHUB_REPO"], mlflow=True)
mlflow.set_experiment("contextsql-day1-smoke-test")
with mlflow.start_run(run_name="hello-dagshub"):
    mlflow.log_param("stage", "day1")
    mlflow.log_metric("setup_ok", 1)
print("MLflow smoke-test logged. Check the Experiments tab on DagHub.")
