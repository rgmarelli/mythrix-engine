# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

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

    result = tools["augment_passage"].invoke(
        {"passage_text": "some text", "focus": "where is joy", "source": "Douay-Rheims", "locator": "Genesis 21:6"}
    )

    assert result == {"augmentation": "Sara laughs."}


def test_augment_passage_prompt_carries_the_passage_and_the_focus(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    client = RecordingChatClient()
    tools = tools_by_name(stores, settings, client)

    tools["augment_passage"].invoke(
        {
            "passage_text": "And Sara said: God hath made a laughter for me.",
            "focus": "where is joy",
            "source": "Douay-Rheims",
            "locator": "Genesis 21:6",
        }
    )

    (prompt,) = client.prompts
    assert "And Sara said: God hath made a laughter for me." in prompt
    assert "where is joy" in prompt


def test_augment_passage_prompt_carries_the_reference(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    """The invocation is told what passage it is reading, so it never has to
    guess a reference from the text — and, when guessing anyway, get it wrong."""
    client = RecordingChatClient()
    tools = tools_by_name(stores, settings, client)

    tools["augment_passage"].invoke(
        {
            "passage_text": "some text",
            "focus": "where is joy",
            "source": "Douay-Rheims",
            "locator": "Genesis 21:5–8",
        }
    )

    (prompt,) = client.prompts
    assert "Douay-Rheims" in prompt
    assert "Genesis 21:5–8" in prompt


def test_augment_passage_prompt_forbids_outside_knowledge_of_the_reference(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    client = RecordingChatClient()
    tools = tools_by_name(stores, settings, client)

    tools["augment_passage"].invoke(
        {"passage_text": "some text", "focus": "where is joy", "source": "Douay-Rheims", "locator": "Genesis 21:6"}
    )

    (prompt,) = client.prompts
    assert "do not draw on outside or prior knowledge" in prompt.lower()


def test_augment_passage_takes_no_retrieval_terms(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    """A region reaches a run because the user is looking at it, not because
    a term matched it, so the tool has no term parameter to leak into the
    prompt and redirect the reading away from the focus. `source`/`locator`
    are the region's own derived identity (FR-AU-15), not a retrieval term."""
    assert set(tools_by_name(stores, settings, FakeChatClient())["augment_passage"].args) == {
        "passage_text",
        "focus",
        "source",
        "locator",
    }


def test_augment_passage_unreachable_model_returns_error(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, RaisingChatClient())

    result = tools["augment_passage"].invoke(
        {"passage_text": "text", "focus": "joy", "source": "Douay-Rheims", "locator": "Genesis 21:6"}
    )

    assert "error" in result
