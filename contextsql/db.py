from sqlalchemy import create_engine
from sqlalchemy.engine import URL

DRIVERS = {"mysql": "mysql+pymysql", "postgresql": "postgresql+psycopg2"}

def make_url(dialect, host=None, port=None, user=None, password=None, database=None):
    if dialect == "sqlite":
        return f"sqlite:///{database}"
    return URL.create(DRIVERS[dialect], username=user, password=password, host=host,
                      port=port, database=database).render_as_string(hide_password=False)

def get_engine(url):
    return create_engine(url, pool_pre_ping=True)
