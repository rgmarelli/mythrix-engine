# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the `summarize_passage` tool."""

from conftest import FakeChatClient, RaisingChatClient

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings


def test_summarize_passage_returns_the_chat_client_response(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient("Fire dominates."))
    result = tools["summarize_passage"].invoke({"passage_text": "some text", "concepts": ["Fire"]})
    assert result == {"summary": "Fire dominates."}


def test_summarize_passage_unreachable_model_returns_error(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, RaisingChatClient())
    result = tools["summarize_passage"].invoke({"passage_text": "some text", "concepts": ["Fire"]})
    assert "error" in result
