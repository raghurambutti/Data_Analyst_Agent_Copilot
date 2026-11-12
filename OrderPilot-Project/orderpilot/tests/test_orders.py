import json

import pytest

from orderpilot.orders import DraftError, price_draft, save_draft


def test_price_comes_from_the_products_table(db):
    draft = price_draft(db, "C001", [{"product_id": "P001", "quantity": 2}, {"product_id": "P007", "quantity": 1}])
    assert draft["total_amount"] == round(24.99 * 2 + 9.99, 2)
    assert draft["items"][0]["name"] == "Wireless Mouse"


@pytest.mark.parametrize(
    "customer, items",
    [
        ("C999", [{"product_id": "P001", "quantity": 1}]),  # unknown customer
        ("C001", [{"product_id": "P999", "quantity": 1}]),  # unknown product
        ("C001", [{"product_id": "P012", "quantity": 1}]),  # retired product
        ("C001", [{"product_id": "P001", "quantity": 0}]),  # zero quantity
        ("C001", [{"product_id": "P001", "quantity": 500}]),  # too many
        ("C001", []),  # empty order
    ],
)
def test_bad_drafts_are_refused(db, customer, items):
    with pytest.raises(DraftError):
        price_draft(db, customer, items)


def test_save_writes_only_to_the_drafts_table(db):
    orders_before = db.query("SELECT COUNT(*) AS n FROM orders")[0]["n"]
    draft = price_draft(db, "C002", [{"product_id": "P003", "quantity": 3}])
    draft_id = save_draft(db, draft, approved_by="tester")

    saved = db.query("SELECT * FROM order_drafts WHERE draft_id = :d", {"d": draft_id})
    assert saved[0]["status"] == "pending_review"
    assert saved[0]["approved_by"] == "tester"
    assert json.loads(saved[0]["items_json"])[0]["quantity"] == 3
    # The real orders table is untouched.
    assert db.query("SELECT COUNT(*) AS n FROM orders")[0]["n"] == orders_before
