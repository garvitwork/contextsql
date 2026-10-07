"""Seed MySQL with synthetic, deliberately messy business data."""
import os, random
from datetime import date, timedelta
import pymysql
from dotenv import load_dotenv

load_dotenv()
random.seed(42)

conn = pymysql.connect(
    host=os.getenv("MYSQL_HOST", "127.0.0.1"), port=int(os.getenv("MYSQL_PORT", 3307)),
    user=os.getenv("MYSQL_USER", "ctx"), password=os.getenv("MYSQL_PASSWORD", "ctxpass"),
    database=os.getenv("MYSQL_DB", "contextsql"), autocommit=False)
cur = conn.cursor()

for t in ["payments", "order_items", "orders", "products", "customers"]:
    cur.execute(f"DELETE FROM {t}")

COUNTRIES = {"India": ["Delhi", "Mumbai", "Bengaluru", "Pune"], "USA": ["Austin", "Boston", "Seattle"],
             "UK": ["London", "Leeds"], "Germany": ["Berlin", "Munich"]}
SEGMENTS = ["consumer", "smb", "enterprise"]
CATS = {"Electronics": (50, 900), "Furniture": (80, 1200), "Office": (5, 120), "Apparel": (10, 150)}
STATUS = (["Shipped"] * 5 + ["shipped", "SHIPPED", "Delivered", "delivered", "Pending"] +
          ["Cancelled", "canceled", "Returned"])
CHANNELS = ["web", "app", "store", "partner", None]
METHODS = ["card", "upi", "bank", "cash"]
today = date.today()

for i in range(1, 501):
    country = random.choice(list(COUNTRIES))
    city = random.choice(COUNTRIES[country]) if random.random() > 0.08 else None
    email = f"user{i}@example.com" if random.random() > 0.1 else None
    cur.execute("INSERT INTO customers (name,email,country,city,segment,created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                (f"Customer {i}", email, country, city, random.choice(SEGMENTS),
                 today - timedelta(days=random.randint(200, 900))))

prices = {}
for i in range(1, 61):
    cat = random.choice(list(CATS)); lo, hi = CATS[cat]
    price = round(random.uniform(lo, hi), 2); prices[i] = price
    cur.execute("INSERT INTO products (name,category,unit_price,cost_price) VALUES (%s,%s,%s,%s)",
                (f"{cat} Item {i}", cat, price, round(price * random.uniform(0.5, 0.8), 2)))

for oid in range(1, 5001):
    odate = today - timedelta(days=random.randint(0, 540))
    status = random.choice(STATUS)
    cur.execute("INSERT INTO orders (customer_id,order_date,status,channel) VALUES (%s,%s,%s,%s)",
                (random.randint(1, 500), odate, status, random.choice(CHANNELS)))
    total = 0
    for _ in range(random.randint(1, 4)):
        pid, qty = random.randint(1, 60), random.randint(1, 5)
        disc = random.choice([None, None, 5, 10, 15, 20])
        cur.execute("INSERT INTO order_items (order_id,product_id,quantity,unit_price,discount_pct) VALUES (%s,%s,%s,%s,%s)",
                    (oid, pid, qty, prices[pid], disc))
        total += qty * prices[pid] * (1 - (disc or 0) / 100)
    if status.lower() not in ("cancelled", "canceled", "pending") and random.random() > 0.05:
        cur.execute("INSERT INTO payments (order_id,amount,payment_date,method) VALUES (%s,%s,%s,%s)",
                    (oid, round(total, 2), odate + timedelta(days=random.randint(0, 5)), random.choice(METHODS)))

conn.commit()
print("Seeded: 500 customers, 60 products, 5000 orders (+ items, payments)")
