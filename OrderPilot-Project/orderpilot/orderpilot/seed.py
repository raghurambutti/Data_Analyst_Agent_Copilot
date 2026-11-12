"""Create the tables and load reproducible fake data.

Run with:  python -m orderpilot.seed

local mode      -> orderpilot_local.db (SQLite)
databricks mode -> <catalog>.<schema>.customers, products, orders, order_items, order_drafts
"""

import random
from datetime import date, timedelta

from orderpilot import config
from orderpilot.db import get_db

FIRST = ["Ava", "Liam", "Mia", "Noah", "Zoe", "Ethan", "Ivy", "Leo", "Nora", "Omar",
         "Priya", "Ravi", "Sara", "Tom", "Uma", "Vik", "Wen", "Yara", "Ben", "Chloe"]
LAST = ["Smith", "Patel", "Garcia", "Kim", "Brown", "Rao", "Lopez", "Chen", "Davis", "Khan"]
CITIES = ["Chicago", "Austin", "Seattle", "Denver", "Boston", "Atlanta"]
PRODUCTS = [
    ("P001", "Wireless Mouse", "Electronics", 24.99, True),
    ("P002", "Mechanical Keyboard", "Electronics", 89.00, True),
    ("P003", "USB-C Hub", "Electronics", 39.50, True),
    ("P004", "Desk Lamp", "Home Office", 32.00, True),
    ("P005", "Ergonomic Chair", "Home Office", 249.00, True),
    ("P006", "Standing Desk", "Home Office", 399.00, True),
    ("P007", "Notebook Pack", "Stationery", 9.99, True),
    ("P008", "Gel Pens (12)", "Stationery", 12.49, True),
    ("P009", "Laptop Stand", "Electronics", 45.00, True),
    ("P010", "Noise-Cancel Headphones", "Electronics", 179.00, True),
    ("P011", "Webcam HD", "Electronics", 59.00, True),
    ("P012", "Old Fax Machine", "Electronics", 120.00, False),  # retired product
]
STATUSES = ["delivered"] * 7 + ["shipped"] * 2 + ["cancelled", "returned"]
CHANNELS = ["web", "web", "mobile"]


def make_data(seed: int = 42):
    """Build rows in memory. The fixed seed makes the data identical on every run."""
    rnd = random.Random(seed)
    customers = []
    for i in range(1, 21):
        name = f"{FIRST[i - 1]} {rnd.choice(LAST)}"
        customers.append((f"C{i:03d}", name, rnd.choice(CITIES), f"2025-{rnd.randint(1, 12):02d}-15"))

    orders, items = [], []
    start = date(2026, 5, 1)
    active = [p for p in PRODUCTS if p[4]]
    for n in range(1, 301):
        order_id = f"O{n:04d}"
        day = start + timedelta(days=rnd.randint(0, 183))
        orders.append((order_id, rnd.choice(customers)[0], day.isoformat(),
                       rnd.choice(STATUSES), rnd.choice(CHANNELS)))
        for product in rnd.sample(active, rnd.randint(1, 3)):
            items.append((order_id, product[0], rnd.randint(1, 4), product[3]))
    return customers, PRODUCTS, orders, items


def _sql_value(value) -> str:
    """Render one Python value as a SQL literal (only used for our own fake data)."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if config.MODE == "databricks" and len(str(value)) == 10 and str(value)[4] == "-" and str(value)[7] == "-":
        return f"DATE'{value}'"  # typed literal for Unity Catalog DATE columns
    return "'" + str(value).replace("'", "''") + "'"


def _insert(db, table_name: str, rows: list[tuple], batch: int = 200) -> None:
    """Insert rows in batches with multi-row VALUES (far fewer round trips)."""
    for i in range(0, len(rows), batch):
        values = ",\n".join("(" + ", ".join(_sql_value(v) for v in row) + ")" for row in rows[i:i + batch])
        db.execute(f"INSERT INTO {config.table(table_name)} VALUES {values}")


def create_tables(db) -> None:
    """(Re)create all five tables with types that suit the current backend."""
    dbx = config.MODE == "databricks"
    text, num, flag, day = ("STRING", "DOUBLE", "BOOLEAN", "DATE") if dbx else ("TEXT", "REAL", "INTEGER", "TEXT")
    whole = "INT" if dbx else "INTEGER"
    create = "CREATE OR REPLACE TABLE" if dbx else "CREATE TABLE"

    if dbx:
        db.execute(f"CREATE SCHEMA IF NOT EXISTS {config.CATALOG}.{config.SCHEMA}")
    else:
        for t in config.READ_TABLES + [config.DRAFTS_TABLE]:
            db.execute(f"DROP TABLE IF EXISTS {t}")

    db.execute(f"{create} {config.table('customers')} (customer_id {text}, name {text}, city {text}, signup_date {day})")
    db.execute(f"{create} {config.table('products')} (product_id {text}, name {text}, category {text}, unit_price {num}, is_active {flag})")
    db.execute(f"{create} {config.table('orders')} (order_id {text}, customer_id {text}, order_date {day}, status {text}, channel {text})")
    db.execute(f"{create} {config.table('order_items')} (order_id {text}, product_id {text}, quantity {whole}, unit_price {num})")
    db.execute(
        f"{create} {config.table(config.DRAFTS_TABLE)} (draft_id {text}, customer_id {text}, items_json {text}, "
        f"total_amount {num}, status {text}, approved_by {text}, created_at {text})"
    )


def seed(db=None, seed_value: int = 42) -> dict:
    """Create tables, load all fake rows, and return the row counts."""
    db = db or get_db()
    create_tables(db)
    customers, products, orders, items = make_data(seed_value)
    _insert(db, "customers", customers)
    _insert(db, "products", products)
    _insert(db, "orders", orders)
    _insert(db, "order_items", items)
    return {"customers": len(customers), "products": len(products), "orders": len(orders), "order_items": len(items)}


if __name__ == "__main__":
    counts = seed()
    print(f"Done! Created fake data in {config.MODE} mode: {counts}")
