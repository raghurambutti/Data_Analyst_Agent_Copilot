"""Drive the Streamlit app headlessly with AppTest and a scripted model."""

import pytest
from langchain_core.messages import AIMessage
from streamlit.testing.v1 import AppTest

from orderpilot import config, llm
from tests.conftest import ScriptedLLM


@pytest.fixture
def app_with(db, monkeypatch):
    """Return a function that starts the app with a given list of model replies."""
    monkeypatch.setattr(config, "LOCAL_DB_PATH", db.path)

    def start(replies):
        monkeypatch.setattr(llm, "make_llm", lambda: ScriptedLLM(responses=replies))
        at = AppTest.from_file("../app.py", default_timeout=30)
        at.run()
        return at

    return start


def test_question_shows_answer_and_sql(app_with):
    at = app_with([
        AIMessage(content="", tool_calls=[{"name": "run_sql", "args": {"query": "SELECT COUNT(*) AS n FROM orders"}, "id": "c1"}]),
        AIMessage(content="There are 300 orders."),
    ])
    at.chat_input[0].set_value("How many orders?").run()

    assert at.chat_message[-1].markdown[0].value == "There are 300 orders."
    assert "SELECT COUNT(*)" in at.chat_message[-1].expander[0].code[0].value


def test_draft_needs_approval_then_saves(app_with, db):
    at = app_with([
        AIMessage(content="", tool_calls=[{"name": "create_order_draft",
                                            "args": {"customer_id": "C004", "items": [{"product_id": "P001", "quantity": 2}]},
                                            "id": "c1"}]),
        AIMessage(content="Saved for review."),
    ])
    at.text_input(key="reviewer").set_value("Raghu").run()
    at.chat_input[0].set_value("Order 2 mice for C004").run()

    assert at.button(key="approve") is not None  # the approval card is showing
    assert db.query("SELECT COUNT(*) AS n FROM order_drafts")[0]["n"] == 0

    at.button(key="approve").click().run()
    saved = db.query("SELECT * FROM order_drafts")
    assert len(saved) == 1 and saved[0]["approved_by"] == "Raghu"
    assert at.chat_message[-1].markdown[0].value == "Saved for review."


def test_reject_saves_nothing(app_with, db):
    at = app_with([
        AIMessage(content="", tool_calls=[{"name": "create_order_draft",
                                            "args": {"customer_id": "C004", "items": [{"product_id": "P001", "quantity": 1}]},
                                            "id": "c1"}]),
        AIMessage(content="Okay, nothing was saved."),
    ])
    at.chat_input[0].set_value("Order a mouse for C004").run()
    at.button(key="reject").click().run()

    assert db.query("SELECT COUNT(*) AS n FROM order_drafts")[0]["n"] == 0
    assert at.chat_message[-1].markdown[0].value == "Okay, nothing was saved."


def test_friendly_error_when_setup_is_missing(db, monkeypatch):
    def broken():
        raise RuntimeError("DATABRICKS_HOST is not set")

    monkeypatch.setattr(config, "LOCAL_DB_PATH", db.path)
    monkeypatch.setattr(llm, "make_llm", broken)
    at = AppTest.from_file("../app.py", default_timeout=30)
    at.run()

    assert not at.exception
    assert "check your .env" in at.error[0].value
    assert at.chat_input[0].disabled
