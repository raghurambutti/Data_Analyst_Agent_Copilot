"""Business rules for order drafts.

price_draft() validates a proposed order and prices it from the products
table. It only reads, and it never trusts prices coming from the model.

save_draft() is the single write in the application. It runs only after a
human approves, and it writes to the order_drafts staging table, never to
the real orders table.
"""

import json
import uuid
from datetime import datetime, timezone

from orderpilot import config

MAX_QUANTITY = 100


class DraftError(ValueError):
    """Raised when a proposed order breaks a business rule."""


def price_draft(db, customer_id: str, items: list[dict]) -> dict:
    """Validate a proposed order and return a priced draft (nothing is saved)."""
    if not items:
        raise DraftError("An order needs at least one item.")

    customers = db.query(
        f"SELECT customer_id, name FROM {config.table('customers')} WHERE customer_id = :cid",
        {"cid": customer_id},
    )
    if not customers:
        raise DraftError(f"Customer '{customer_id}' does not exist.")

    lines = []
    total = 0.0
    for item in items:
        pid = str(item.get("product_id", "")).strip()
        qty = int(item.get("quantity", 0))
        if qty < 1 or qty > MAX_QUANTITY:
            raise DraftError(f"Quantity for {pid} must be between 1 and {MAX_QUANTITY}.")

        found = db.query(
            f"SELECT product_id, name, unit_price, is_active "
            f"FROM {config.table('products')} WHERE product_id = :pid",
            {"pid": pid},
        )
        if not found:
            raise DraftError(f"Product '{pid}' does not exist.")
        product = found[0]
        if not product["is_active"]:
            raise DraftError(f"Product '{pid}' is no longer for sale.")

        line_total = round(float(product["unit_price"]) * qty, 2)
        total += line_total
        lines.append(
            {
                "product_id": pid,
                "name": product["name"],
                "quantity": qty,
                "unit_price": float(product["unit_price"]),
                "line_total": line_total,
            }
        )

    return {
        "customer_id": customer_id,
        "customer_name": customers[0]["name"],
        "items": lines,
        "total_amount": round(total, 2),
    }


def save_draft(db, draft: dict, approved_by: str) -> str:
    """Insert an approved draft into the staging table and return its id."""
    draft_id = "DRAFT-" + uuid.uuid4().hex[:8].upper()
    db.execute(
        f"INSERT INTO {config.table(config.DRAFTS_TABLE)} "
        "(draft_id, customer_id, items_json, total_amount, status, approved_by, created_at) "
        "VALUES (:draft_id, :customer_id, :items_json, :total_amount, :status, :approved_by, :created_at)",
        {
            "draft_id": draft_id,
            "customer_id": draft["customer_id"],
            "items_json": json.dumps(draft["items"]),
            "total_amount": draft["total_amount"],
            "status": "pending_review",
            "approved_by": approved_by,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
    return draft_id
