"""Unit tests for `build_tools` itself — the composition of the seven tools."""

from conftest import FakeChatClient

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings


def test_build_tools_returns_exactly_the_seven_read_only_tools(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    assert set(tools) == {
        "list_semiotic_systems",
        "list_traditions",
        "list_signs",
        "get_sign",
        "query_sign",
        "fetch_segments",
        "summarize_passage",
    }
