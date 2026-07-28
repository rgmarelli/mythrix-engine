"""Unit tests for the `list_signs` tool."""

from conftest import FakeChatClient

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings


def test_list_signs_scoped_by_semiotic_system(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["list_signs"].invoke({"semiotic_system": "tarot"})
    assert {s["slug"] for s in result} == {"the-tower", "the-magician"}
    the_magician = next(s for s in result if s["slug"] == "the-magician")
    assert set(the_magician["traditions"]) == {"rider-waite", "marseille"}


def test_list_signs_unscoped_includes_every_system(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["list_signs"].invoke({})
    assert {s["slug"] for s in result} == {"the-tower", "the-magician", "hebrew-letter-peh"}
