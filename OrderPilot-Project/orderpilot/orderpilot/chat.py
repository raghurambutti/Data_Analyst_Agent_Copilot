"""Terminal chat for OrderPilot.

Run with:  python -m orderpilot.chat
"""

import uuid

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from orderpilot import config, llm
from orderpilot.db import get_db
from orderpilot.graph import build_graph


def show_draft(draft: dict) -> None:
    """Print a priced draft so the reviewer can decide."""
    print("\n  ---- ORDER DRAFT (waiting for your approval) ----")
    print(f"  Customer: {draft['customer_name']} ({draft['customer_id']})")
    for line in draft["items"]:
        print(
            f"   - {line['quantity']} x {line['name']} ({line['product_id']}) "
            f"@ ${line['unit_price']:.2f} = ${line['line_total']:.2f}"
        )
    print(f"  TOTAL: ${draft['total_amount']:.2f}")
    print("  -------------------------------------------------\n")


def main() -> None:
    graph = build_graph(llm.make_llm(), get_db(), checkpointer=InMemorySaver())
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}}  # one conversation
    reviewer = input("Your name (for approvals): ").strip() or "reviewer"

    print(f"\nOrderPilot is ready ({config.MODE} mode). Type 'quit' to stop.\n")
    while True:
        question = input("You: ").strip()
        if question.lower() in ("quit", "exit", "q"):
            break
        if not question:
            continue

        result = graph.invoke({"messages": [HumanMessage(question)]}, thread)

        # The graph pauses on interrupt(); ask the human, then resume it.
        while result.get("__interrupt__"):
            show_draft(result["__interrupt__"][0].value["draft"])
            answer = input("Approve this order? (yes/no): ").strip().lower()
            decision = {"approved": answer.startswith("y"), "reviewer": reviewer}
            result = graph.invoke(Command(resume=decision), thread)

        print(f"\nOrderPilot: {result['messages'][-1].content}\n")


if __name__ == "__main__":
    main()
