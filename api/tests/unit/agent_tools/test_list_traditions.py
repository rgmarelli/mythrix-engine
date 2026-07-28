"""Unit tests for the `list_traditions` tool."""

from conftest import FakeChatClient

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings


def test_list_traditions_unscoped(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["list_traditions"].invoke({})
    assert {t["slug"] for t in result} == {"rider-waite", "marseille", "golden-dawn-kabbalah"}


def test_list_traditions_scoped_by_semiotic_system(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["list_traditions"].invoke({"semiotic_system": "hebrew_alef_bet"})
    assert {t["slug"] for t in result} == {"golden-dawn-kabbalah"}
