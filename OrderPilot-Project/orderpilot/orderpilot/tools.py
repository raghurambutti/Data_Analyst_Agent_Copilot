"""Tools the model can call.

The model never touches the database directly. It can only request:

    get_schema          -> list allowed tables and their columns
    run_sql             -> run one guarded, read-only SELECT
    create_order_draft  -> propose an order (routed to human approval)
"""

import json

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from orderpilot import config
from orderpilot.safety import UnsafeSQLError, check_sql


def make_read_tools(db):
    """Build the read-only tools bound to one database connection."""

    @tool
    def get_schema() -> str:
        """List the tables you can query and their columns. Call this first."""
        lines = []
        for name in config.READ_TABLES:
            full = config.table(name)
            rows = db.query(f"SELECT * FROM {full} LIMIT 1")
            columns = ", ".join(rows[0].keys()) if rows else "(empty table)"
            lines.append(f"{full}: {columns}")
        return "\n".join(lines)

    @tool
    def run_sql(query: str) -> str:
        """Run ONE read-only SELECT query on the order tables and return the rows as JSON."""
        try:
            safe_query = check_sql(query)
        except UnsafeSQLError as err:
            return f"BLOCKED by safety guard: {err}"
        try:
            rows = db.query(safe_query)
        except Exception as err:  # wrong column, typo, etc.: let the model retry
            return f"SQL error: {err}. Fix the query and try again."
        return json.dumps(rows, default=str)

    return [get_schema, run_sql]


class OrderItem(BaseModel):
    product_id: str = Field(description="Product id, for example P003")
    quantity: int = Field(description="How many units, 1 to 100")


@tool
def create_order_draft(customer_id: str, items: list[OrderItem]) -> str:
    """Propose a new order for a customer. A human must approve it before it is saved.
    Prices are looked up automatically; do not invent them."""
    # Never executed: the graph routes this call to the human_approval node.
    return "This tool is handled by the human approval step."


DRAFT_TOOL_NAME = create_order_draft.name
