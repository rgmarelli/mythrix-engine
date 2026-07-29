"""Unit tests for the `analyze_passage` tool — one region read against the
run's focus (FR-DS-16)."""

from conftest import FakeChatClient, RaisingChatClient

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings


class RecordingChatClient:
    generation_model = "fake-model"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "a finding"


def test_analyze_passage_returns_the_chat_client_response_under_finding(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient("Sara laughs."))

    result = tools["analyze_passage"].invoke(
        {"passage_text": "some text", "focus": "where is joy", "concepts": ["laughter"]}
    )

    assert result == {"finding": "Sara laughs."}


def test_analyze_passage_prompt_carries_the_passage_focus_and_terms(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    client = RecordingChatClient()
    tools = tools_by_name(stores, settings, client)

    tools["analyze_passage"].invoke(
        {
            "passage_text": "And Sara said: God hath made a laughter for me.",
            "focus": "where is joy",
            "concepts": ["laughter", "mirth"],
        }
    )

    (prompt,) = client.prompts
    assert "And Sara said: God hath made a laughter for me." in prompt
    assert "where is joy" in prompt
    assert "laughter, mirth" in prompt


def test_analyze_passage_unreachable_model_returns_error(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, RaisingChatClient())

    result = tools["analyze_passage"].invoke({"passage_text": "text", "focus": "joy", "concepts": ["laughter"]})

    assert "error" in result
