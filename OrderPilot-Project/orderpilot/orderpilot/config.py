"""Central settings for OrderPilot.

Every value comes from environment variables (loaded from a local .env file),
so no secrets or workspace details are ever hard-coded in the source.
"""

import os

from dotenv import load_dotenv

load_dotenv()  # read .env into os.environ (does nothing if the file is missing)

# "local" = SQLite file for development, "databricks" = Unity Catalog tables.
MODE = os.getenv("ORDERPILOT_MODE", "local").lower()

# Unity Catalog three-level namespace: catalog.schema.table
CATALOG = os.getenv("ORDERPILOT_CATALOG", "workspace")
SCHEMA = os.getenv("ORDERPILOT_SCHEMA", "orderpilot")

# SQLite file used in local mode.
LOCAL_DB_PATH = os.getenv("ORDERPILOT_LOCAL_DB", "orderpilot_local.db")

# Name of the Databricks Model Serving endpoint that hosts the chat model.
LLM_ENDPOINT = os.getenv("LLM_ENDPOINT", "databricks-meta-llama-3-3-70b-instruct")

# SQL warehouse: give either the full HTTP path or just the warehouse ID.
DATABRICKS_HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH", "")
DATABRICKS_WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "")

# Tables the agent may read, and the single table it may write to.
READ_TABLES = ["customers", "products", "orders", "order_items"]
DRAFTS_TABLE = "order_drafts"

# Upper bound on rows returned by any one agent query.
MAX_ROWS = 50


def table(name: str) -> str:
    """Return the table name to use in SQL for the current mode."""
    if MODE == "databricks":
        return f"{CATALOG}.{SCHEMA}.{name}"
    return name


def databricks_http_path() -> str:
    """HTTP path of the SQL warehouse, built from the warehouse ID if needed."""
    if DATABRICKS_HTTP_PATH:
        return DATABRICKS_HTTP_PATH
    if DATABRICKS_WAREHOUSE_ID:
        return f"/sql/1.0/warehouses/{DATABRICKS_WAREHOUSE_ID}"
    return ""
