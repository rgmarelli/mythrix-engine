"""Unit tests for the `consolidate_findings` tool — the single answer across a
run's readings (FR-DS-17)."""

from conftest import FakeChatClient, RaisingChatClient

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings

_FINDINGS = [
    {"label": "[R1] Douay-Rheims, Genesis 21:6", "finding": "Sara laughs."},
    {"label": "[R2] Douay-Rheims, Luke 6:21", "finding": "Weeping turns to laughter."},
]


class RecordingChatClient:
    generation_model = "fake-model"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "a consolidation"


def test_consolidate_findings_returns_the_chat_client_response(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient("Joy recurs as reversal [R1][R2]."))

    result = tools["consolidate_findings"].invoke(
        {"focus": "where is joy", "findings": _FINDINGS, "concepts": ["laughter"]}
    )

    assert result == {"consolidation": "Joy recurs as reversal [R1][R2]."}


def test_consolidation_prompt_carries_the_labeled_findings_and_the_focus(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    client = RecordingChatClient()
    tools = tools_by_name(stores, settings, client)

    tools["consolidate_findings"].invoke({"focus": "where is joy", "findings": _FINDINGS, "concepts": ["laughter"]})

    (prompt,) = client.prompts
    assert "[R1] Douay-Rheims, Genesis 21:6" in prompt
    assert "Sara laughs." in prompt
    assert "Weeping turns to laughter." in prompt
    assert "where is joy" in prompt


def test_consolidation_prompt_asks_for_region_markers(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    """FR-DS-21: the `[R#]` labels are this prompt's marker vocabulary, and
    the only markers the report carries."""
    client = RecordingChatClient()
    tools = tools_by_name(stores, settings, client)

    tools["consolidate_findings"].invoke({"focus": "joy", "findings": _FINDINGS, "concepts": ["laughter"]})

    (prompt,) = client.prompts
    assert "[R1]" in prompt
    assert "[S1]" not in prompt
    assert "[G1]" not in prompt


def test_consolidate_findings_unreachable_model_returns_error(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, RaisingChatClient())

    result = tools["consolidate_findings"].invoke({"focus": "joy", "findings": _FINDINGS, "concepts": ["laughter"]})

    assert "error" in result
