"""Unit tests for the `get_sign` tool."""

from conftest import FakeChatClient

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings


def test_get_sign_auto_resolves_single_tradition_sign(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "the-tower"})
    assert result["sign"] == "The Tower"
    assert result["tradition"] == "Rider-Waite-Smith"
    assert result["interpretants"] == [{"type": "element", "value": "Fire"}]


def test_get_sign_needs_tradition_for_multi_tradition_sign(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "the-magician"})
    assert result == {
        "needs_tradition": True,
        "sign": "The Magician",
        "traditions": ["rider-waite", "marseille"],
    }


def test_get_sign_with_tradition_returns_facts_and_citations(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "the-magician", "tradition": "rider-waite"})
    assert result["display_name"] == "The Magician"
    assert result["citations"] == [{"source": "The Pictorial Key to the Tarot", "locator": "p. 71"}]


def test_get_sign_unknown_slug_returns_error(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "nonexistent"})
    assert "error" in result


def test_get_sign_resolves_by_canonical_name_not_only_slug(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    """A real failure mode: the model derives `sign` from the user's own
    wording ("The Magician") before any tool has surfaced the slug
    ("the-magician") — the spec's own `get_sign` example uses exactly this
    display-name phrasing, so slug-only matching must not be the only path."""
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "The Magician", "tradition": "rider-waite"})
    assert result["display_name"] == "The Magician"
    assert "error" not in result


def test_get_sign_name_match_is_case_and_whitespace_insensitive(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "  the magician  ", "tradition": "rider-waite"})
    assert result["display_name"] == "The Magician"


def test_get_sign_unknown_tradition_returns_error(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "the-tower", "tradition": "nonexistent"})
    assert "error" in result
