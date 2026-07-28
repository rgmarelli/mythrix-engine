"""Unit tests for the `list_semiotic_systems` tool."""

from conftest import FakeChatClient

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings


def test_list_semiotic_systems(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["list_semiotic_systems"].invoke({})
    assert result == ["hebrew_alef_bet", "tarot"]
