"""End-to-end tests of the LangGraph flow with a scripted model."""

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from orderpilot.graph import build_graph
from tests.conftest import ScriptedLLM

THREAD = {"configurable": {"thread_id": "test-thread"}}


def tool_call(name, args, call_id="call_1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def test_question_uses_run_sql_and_answers(db):
    llm = ScriptedLLM(responses=[
        tool_call("run_sql", {"query": "SELECT COUNT(*) AS n FROM orders"}),
        AIMessage(content="There are 300 orders."),
    ])
    graph = build_graph(llm, db, InMemorySaver())
    result = graph.invoke({"messages": [HumanMessage("How many orders?")]}, THREAD)

    tool_output = result["messages"][-2].content
    assert '"n": 300' in tool_output
    assert result["messages"][-1].content == "There are 300 orders."


def test_dangerous_sql_is_blocked_inside_the_graph(db):
    llm = ScriptedLLM(responses=[
        tool_call("run_sql", {"query": "DELETE FROM orders"}),
        AIMessage(content="I can't do that."),
    ])
    graph = build_graph(llm, db, InMemorySaver())
    result = graph.invoke({"messages": [HumanMessage("Delete everything")]}, THREAD)

    assert "BLOCKED" in result["messages"][-2].content
    assert db.query("SELECT COUNT(*) AS n FROM orders")[0]["n"] == 300


def _draft_llm():
    return ScriptedLLM(responses=[
        tool_call("create_order_draft", {"customer_id": "C001", "items": [{"product_id": "P002", "quantity": 1}]}),
        AIMessage(content="Done."),
    ])


def test_draft_pauses_and_saves_after_yes(db):
    graph = build_graph(_draft_llm(), db, InMemorySaver())
    result = graph.invoke({"messages": [HumanMessage("Order a keyboard for C001")]}, THREAD)

    # Paused: nothing saved yet.
    assert result["__interrupt__"][0].value["draft"]["total_amount"] == 89.0
    assert db.query("SELECT COUNT(*) AS n FROM order_drafts")[0]["n"] == 0

    result = graph.invoke(Command(resume={"approved": True, "reviewer": "Raghu"}), THREAD)
    saved = db.query("SELECT * FROM order_drafts")
    assert len(saved) == 1 and saved[0]["approved_by"] == "Raghu"
    assert "APPROVED" in result["messages"][-2].content


def test_draft_rejected_saves_nothing(db):
    graph = build_graph(_draft_llm(), db, InMemorySaver())
    graph.invoke({"messages": [HumanMessage("Order a keyboard for C001")]}, THREAD)
    result = graph.invoke(Command(resume={"approved": False}), THREAD)

    assert db.query("SELECT COUNT(*) AS n FROM order_drafts")[0]["n"] == 0
    assert "REJECTED" in result["messages"][-2].content


def test_invalid_draft_never_reaches_the_human(db):
    llm = ScriptedLLM(responses=[
        tool_call("create_order_draft", {"customer_id": "C001", "items": [{"product_id": "P012", "quantity": 1}]}),
        AIMessage(content="That product is retired."),
    ])
    graph = build_graph(llm, db, InMemorySaver())
    result = graph.invoke({"messages": [HumanMessage("Order a fax machine")]}, THREAD)

    assert not result.get("__interrupt__")
    assert "not valid" in result["messages"][-2].content
