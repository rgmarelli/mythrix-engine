"""Unit tests for the `query_sign` tool."""

from conftest import FakeChatClient

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings


def test_query_sign_returns_regions_dict(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["query_sign"].invoke({"sign": "the-tower", "tradition": "rider-waite"})
    assert result == {"regions": []}


def test_query_sign_resolves_by_canonical_name_not_only_slug(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["query_sign"].invoke({"sign": "The Tower", "tradition": "rider-waite"})
    assert result == {"regions": []}
    assert "error" not in result


def test_query_sign_unknown_sign_returns_error(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["query_sign"].invoke({"sign": "nonexistent", "tradition": "rider-waite"})
    assert "error" in result
