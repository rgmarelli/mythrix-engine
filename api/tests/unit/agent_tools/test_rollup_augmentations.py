"""Unit tests for the `rollup_augmentations` tool — the further synthesis
above a run's first consolidation level (FR-AU-39, ADR-016)."""

from conftest import FakeChatClient, RaisingChatClient

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings

_SUMMARIES = [
    "Joy recurs as reversal [R1][R2].",
    "Sorrow precedes joy in every passage examined [R3][R4].",
]


class RecordingChatClient:
    generation_model = "fake-model"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "a rollup"


def test_rollup_augmentations_returns_the_chat_client_response(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient("Joy consistently reverses sorrow [R1][R2][R3][R4]."))

    result = tools["rollup_augmentations"].invoke({"focus": "where is joy", "summaries": _SUMMARIES})

    assert result == {"consolidation": "Joy consistently reverses sorrow [R1][R2][R3][R4]."}


def test_rollup_prompt_carries_the_summaries_and_the_focus(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    client = RecordingChatClient()
    tools = tools_by_name(stores, settings, client)

    tools["rollup_augmentations"].invoke({"focus": "where is joy", "summaries": _SUMMARIES})

    (prompt,) = client.prompts
    assert "Joy recurs as reversal [R1][R2]." in prompt
    assert "Sorrow precedes joy in every passage examined [R3][R4]." in prompt
    assert "where is joy" in prompt


def test_rollup_prompt_instructs_preserving_markers_verbatim(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    """FR-AU-39: a rollup invocation is given no label vocabulary of its own —
    it must carry forward whatever markers its inputs already carry."""
    client = RecordingChatClient()
    tools = tools_by_name(stores, settings, client)

    tools["rollup_augmentations"].invoke({"focus": "joy", "summaries": _SUMMARIES})

    (prompt,) = client.prompts
    assert "exactly as written" in prompt
    assert "Never invent a new marker" in prompt


def test_rollup_augmentations_unreachable_model_returns_error(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, RaisingChatClient())

    result = tools["rollup_augmentations"].invoke({"focus": "joy", "summaries": _SUMMARIES})

    assert "error" in result
