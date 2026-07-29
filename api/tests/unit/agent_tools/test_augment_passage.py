"""Unit tests for the `augment_passage` tool — one region read against the
run's focus (FR-AU-19)."""

from conftest import FakeChatClient, RaisingChatClient

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings


class RecordingChatClient:
    generation_model = "fake-model"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "an augmentation"


def test_augment_passage_returns_the_chat_client_response_under_augmentation(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient("Sara laughs."))

    result = tools["augment_passage"].invoke({"passage_text": "some text", "focus": "where is joy"})

    assert result == {"augmentation": "Sara laughs."}


def test_augment_passage_prompt_carries_the_passage_and_the_focus(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    client = RecordingChatClient()
    tools = tools_by_name(stores, settings, client)

    tools["augment_passage"].invoke(
        {"passage_text": "And Sara said: God hath made a laughter for me.", "focus": "where is joy"}
    )

    (prompt,) = client.prompts
    assert "And Sara said: God hath made a laughter for me." in prompt
    assert "where is joy" in prompt


def test_augment_passage_takes_no_retrieval_terms(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    """A region reaches a run because the user is looking at it, not because
    a term matched it, so the tool has no term parameter to leak into the
    prompt and redirect the reading away from the focus."""
    assert set(tools_by_name(stores, settings, FakeChatClient())["augment_passage"].args) == {
        "passage_text",
        "focus",
    }


def test_augment_passage_unreachable_model_returns_error(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, RaisingChatClient())

    result = tools["augment_passage"].invoke({"passage_text": "text", "focus": "joy"})

    assert "error" in result
