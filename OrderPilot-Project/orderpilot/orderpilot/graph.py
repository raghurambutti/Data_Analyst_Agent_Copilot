"""The LangGraph agent.

    START -> agent --(no tool call)----------------> END
               |
               +--(get_schema / run_sql)-----------> tools ----------> agent
               |
               +--(create_order_draft)-------------> human_approval -> agent

human_approval pauses the graph with interrupt() and writes only after "yes".
"""

from pathlib import Path

from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

from orderpilot.orders import DraftError, price_draft, save_draft
from orderpilot.tools import DRAFT_TOOL_NAME, create_order_draft, make_read_tools

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system.md").read_text()


def _as_dict(item) -> dict:
    """Tool args may arrive as dicts or pydantic models; normalise to dict."""
    return item.model_dump() if hasattr(item, "model_dump") else dict(item)


def _is_approved(decision) -> tuple[bool, str]:
    """Interpret the resume value: a dict, a "yes"/"no" string, or a bool."""
    if isinstance(decision, dict):
        return bool(decision.get("approved")), str(decision.get("reviewer", "unknown"))
    if isinstance(decision, str):
        return decision.strip().lower() in ("y", "yes", "approve", "approved"), "unknown"
    return bool(decision), "unknown"


def build_graph(llm, db, checkpointer=None):
    """Assemble and compile the agent graph."""
    read_tools = make_read_tools(db)
    tools_by_name = {t.name: t for t in read_tools}
    llm_with_tools = llm.bind_tools(read_tools + [create_order_draft])

    def agent(state: MessagesState):
        messages = [SystemMessage(SYSTEM_PROMPT)] + state["messages"]
        return {"messages": [llm_with_tools.invoke(messages)]}

    def route(state: MessagesState):
        last = state["messages"][-1]
        calls = getattr(last, "tool_calls", None) or []
        if not calls:
            return END
        if any(call["name"] == DRAFT_TOOL_NAME for call in calls):
            return "human_approval"
        return "tools"

    def human_approval(state: MessagesState):
        last = state["messages"][-1]
        results = []
        draft_handled = False

        for call in last.tool_calls:
            # Read tools requested in the same turn: just run them.
            if call["name"] != DRAFT_TOOL_NAME:
                tool = tools_by_name.get(call["name"])
                output = tool.invoke(call["args"]) if tool else f"Unknown tool {call['name']}"
                results.append(ToolMessage(content=str(output), tool_call_id=call["id"]))
                continue

            # One draft per turn: the node re-runs from the top on resume,
            # so a second interrupt would repeat the first draft's write.
            if draft_handled:
                results.append(
                    ToolMessage(
                        content="Only one draft can be approved at a time. Ask again after this one.",
                        tool_call_id=call["id"],
                    )
                )
                continue
            draft_handled = True

            # Step A: validate and price (read only, safe to repeat on resume).
            try:
                items = [_as_dict(i) for i in call["args"].get("items", [])]
                draft = price_draft(db, call["args"].get("customer_id", ""), items)
            except (DraftError, ValueError, TypeError) as err:
                results.append(
                    ToolMessage(content=f"Draft not valid: {err}", tool_call_id=call["id"])
                )
                continue

            # Step B: pause until a human answers.
            decision = interrupt({"question": "Approve this order draft?", "draft": draft})
            approved, reviewer = _is_approved(decision)

            # Step C: the only write, after "yes".
            if approved:
                draft_id = save_draft(db, draft, approved_by=reviewer)
                text = (
                    f"APPROVED by {reviewer}. Saved as {draft_id} with status pending_review. "
                    f"Total ${draft['total_amount']:.2f}."
                )
            else:
                text = "REJECTED by the human reviewer. Nothing was saved."
            results.append(ToolMessage(content=text, tool_call_id=call["id"]))

        return {"messages": results}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(read_tools))
    graph.add_node("human_approval", human_approval)

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, ["tools", "human_approval", END])
    graph.add_edge("tools", "agent")
    graph.add_edge("human_approval", "agent")

    return graph.compile(checkpointer=checkpointer)
