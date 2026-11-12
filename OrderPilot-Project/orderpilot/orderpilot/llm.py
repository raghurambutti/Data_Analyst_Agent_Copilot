"""Factory for the chat model.

Keeping this in one place means the terminal chat, the Streamlit app and the
tests all get the model the same way, and tests can swap in a fake model.
"""

from orderpilot import config


def make_llm():
    """Return a LangChain chat model served by a Databricks Model Serving endpoint."""
    from databricks_langchain import ChatDatabricks

    # temperature=0 makes answers as repeatable as possible, which matters for SQL.
    return ChatDatabricks(endpoint=config.LLM_ENDPOINT, temperature=0)
