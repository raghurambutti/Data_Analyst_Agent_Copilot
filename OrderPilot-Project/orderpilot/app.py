"""OrderPilot web app (Streamlit).

Run locally:            streamlit run app.py
Deploy as Databricks App: see app.yaml and the README.
"""

import uuid

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from orderpilot import config, llm
from orderpilot.db import get_db
from orderpilot.graph import build_graph

st.set_page_config(page_title="OrderPilot", layout="centered")


def start_session() -> None:
    """Create the agent once per browser session; Streamlit reruns this file on every click."""
    st.session_state.thread = {"configurable": {"thread_id": str(uuid.uuid4())}}
    st.session_state.chat = []  # what we draw: {"role", "text", "sql"}
    st.session_state.pending = None  # a draft waiting for approval
    st.session_state.error = None
    try:
        st.session_state.graph = build_graph(llm.make_llm(), get_db(), checkpointer=InMemorySaver())
    except Exception as err:  # missing .env values, unreachable workspace...
        st.session_state.graph = None
        st.session_state.error = f"Could not start the agent, check your .env. {type(err).__name__}: {err}"


def sql_used(messages) -> list[str]:
    """SQL the agent ran since the user's last message, for the 'How I got this' panel."""
    queries = []
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            break
        if isinstance(msg, AIMessage):
            queries += [c["args"].get("query", "") for c in msg.tool_calls if c["name"] == "run_sql"]
    return list(reversed(queries))


def run_agent(payload) -> None:
    """Send a message (or an approval) to the graph and store what comes back."""
    if st.session_state.graph is None:
        return
    try:
        result = st.session_state.graph.invoke(payload, st.session_state.thread)
    except Exception as err:  # bad credentials, warehouse asleep, endpoint name typo...
        st.session_state.error = f"{type(err).__name__}: {err}"
        return
    st.session_state.error = None
    if result.get("__interrupt__"):
        st.session_state.pending = result["__interrupt__"][0].value["draft"]
        return
    st.session_state.pending = None
    st.session_state.chat.append(
        {"role": "assistant", "text": result["messages"][-1].content, "sql": sql_used(result["messages"])}
    )


def decide(approved: bool) -> None:
    """Button callback: resume the paused graph with the human's decision."""
    reviewer = st.session_state.get("reviewer") or "reviewer"
    run_agent(Command(resume={"approved": approved, "reviewer": reviewer}))


if "graph" not in st.session_state:
    start_session()

with st.sidebar:
    st.header("OrderPilot")
    st.caption(f"Data: **{config.MODE}**  \nModel: `{config.LLM_ENDPOINT}`")
    st.text_input("Your name (for approvals)", key="reviewer")
    if st.button("New conversation"):
        start_session()
        st.rerun()

st.title("OrderPilot")
st.caption("Ask about orders, or ask me to draft one. Drafts are saved only after you approve.")

for entry in st.session_state.chat:
    with st.chat_message(entry["role"]):
        st.markdown(entry["text"])
        if entry.get("sql"):
            with st.expander("How I got this"):
                for query in entry["sql"]:
                    st.code(query, language="sql")

if st.session_state.error:
    st.error(st.session_state.error)

draft = st.session_state.pending
if draft:
    with st.container(border=True):
        st.subheader("Order draft: waiting for your approval")
        st.write(f"Customer: **{draft['customer_name']}** ({draft['customer_id']})")
        st.table(
            [
                {"Product": f"{i['name']} ({i['product_id']})", "Qty": i["quantity"],
                 "Unit price": f"${i['unit_price']:.2f}", "Line total": f"${i['line_total']:.2f}"}
                for i in draft["items"]
            ]
        )
        st.write(f"**Total: ${draft['total_amount']:.2f}**")
        left, right = st.columns(2)
        left.button("Approve", type="primary", key="approve", on_click=decide, args=(True,))
        right.button("Reject", key="reject", on_click=decide, args=(False,))

question = st.chat_input("Ask about your orders...", disabled=draft is not None or st.session_state.graph is None)
if question:
    st.session_state.chat.append({"role": "user", "text": question})
    with st.spinner("Thinking..."):
        run_agent({"messages": [HumanMessage(question)]})
    st.rerun()
