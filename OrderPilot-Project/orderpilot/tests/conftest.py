"""Shared pytest fixtures: a seeded throwaway database and a scripted model."""

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel

from orderpilot import config
from orderpilot.db import LocalDB
from orderpilot.seed import seed


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A fresh SQLite database with the fake data, deleted after each test."""
    monkeypatch.setattr(config, "MODE", "local")
    database = LocalDB(str(tmp_path / "test.db"))
    seed(database)
    return database


class ScriptedLLM(FakeMessagesListChatModel):
    """Fake chat model that returns the given messages in order.
    Lets tests run offline, for free, and with deterministic results."""

    def bind_tools(self, tools, **kwargs):
        return self  # the real model needs tool schemas; the fake one ignores them
