"""Sanity check: row counts + a messy-status peek."""
import os, pymysql
from dotenv import load_dotenv
load_dotenv()
conn = pymysql.connect(host=os.getenv("MYSQL_HOST"), port=int(os.getenv("MYSQL_PORT")),
                       user=os.getenv("MYSQL_USER"), password=os.getenv("MYSQL_PASSWORD"),
                       database=os.getenv("MYSQL_DB"))
cur = conn.cursor()
for t in ["customers", "products", "orders", "order_items", "payments", "business_glossary", "query_log"]:
    cur.execute(f"SELECT COUNT(*) FROM {t}"); print(f"{t:18} {cur.fetchone()[0]}")
cur.execute("SELECT status, COUNT(*) FROM orders GROUP BY status ORDER BY 2 DESC")
print("\norder statuses:", cur.fetchall())
