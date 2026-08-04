# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the `get_sign` tool."""

from conftest import FakeChatClient

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings


def test_get_sign_auto_resolves_single_tradition_sign(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "the-tower"})
    assert result["sign"] == "the-tower"
    assert result["tradition"] == "rider-waite"
    assert result["interpretants"] == [{"type": "element", "value": "Fire"}]


def test_get_sign_carries_display_names_beside_identities(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    """Identity keys carry slugs; a reply is composed from the `*_name`
    companions (ADR-014), so both must be present and distinct."""
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "the-tower"})
    assert result["sign_name"] == "The Tower"
    assert result["tradition_name"] == "Rider-Waite-Smith"


def test_get_sign_needs_tradition_for_multi_tradition_sign(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "the-magician"})
    assert result == {
        "needs_tradition": True,
        "sign": "the-magician",
        "sign_name": "The Magician",
        "traditions": [
            {"slug": "rider-waite", "name": "Rider-Waite-Smith"},
            {"slug": "marseille", "name": "Tarot de Marseille"},
        ],
    }


def test_get_sign_with_tradition_returns_facts_and_citations(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "the-magician", "tradition": "rider-waite"})
    assert result["display_name"] == "The Magician"
    assert len(result["citations"]) == 1
    citation = result["citations"][0]
    assert citation["source"] == "The Pictorial Key to the Tarot"
    assert citation["locator"] == "p. 71"
    assert citation["grounding_id"].startswith("G")
    assert len(citation["grounding_id"]) > 1


def test_get_sign_citation_grounding_ids_are_independently_generated(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    """ADR-022: two calls returning the same citation must not reuse the same
    id — it is opaque and independently generated per render, not derived
    from the citation's content or position."""
    tools = tools_by_name(stores, settings, FakeChatClient())
    first = tools["get_sign"].invoke({"sign": "the-magician", "tradition": "rider-waite"})
    second = tools["get_sign"].invoke({"sign": "the-magician", "tradition": "rider-waite"})
    assert first["citations"][0]["grounding_id"] != second["citations"][0]["grounding_id"]


def test_get_sign_unknown_slug_returns_error(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "nonexistent"})
    assert "error" in result


def test_get_sign_unknown_sign_error_lists_available_signs(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "nonexistent"})
    assert "The Tower" in result["error"]
    assert "The Magician" in result["error"]
    assert "Peh" in result["error"]


def test_get_sign_unknown_sign_error_scopes_the_list_to_the_given_tradition(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "nonexistent", "tradition": "rider-waite"})
    assert "The Tower" in result["error"]
    assert "The Magician" in result["error"]
    assert "Peh" not in result["error"]


def test_get_sign_resolves_a_shortened_name_by_containment(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    """A real failure mode: the model drops a sign's leading article
    ("Magician" instead of "The Magician"). Containment in either direction
    must still resolve it, as long as exactly one sign matches."""
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "Magician", "tradition": "rider-waite"})
    assert result["display_name"] == "The Magician"
    assert "error" not in result


def test_get_sign_ambiguous_containment_match_returns_error_not_a_guess(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    """ "the" is contained in both "The Tower" and "The Magician" — resolving
    to either would be a silent guess, so this must fail closed rather than
    pick one."""
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "the"})
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


def test_get_sign_resolves_tradition_by_name_not_only_slug(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    """A tradition's slug and its display name are unrelated strings
    ("marseille" / "Tarot de Marseille"), and a request names it the way the
    user said it — before any tool has surfaced the slug."""
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "the-magician", "tradition": "Tarot de Marseille"})
    assert "error" not in result
    assert result["tradition"] == "marseille"
    assert result["display_name"] == "Le Bateleur"


def test_get_sign_tradition_match_is_case_and_whitespace_insensitive(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    for spelling in ("Rider-Waite-Smith", "  rider-waite  ", "RIDER-WAITE"):
        result = tools["get_sign"].invoke({"sign": "the-magician", "tradition": spelling})
        assert result["tradition"] == "rider-waite", spelling


def test_get_sign_tradition_the_sign_lacks_returns_manifestation_error(
    stores: Stores, settings: Settings, tools_by_name
) -> None:  # noqa: ANN001
    """A real tradition the sign has no manifestation in resolves, then fails
    at the store with the more specific error — resolution is deliberately not
    scoped to the sign's own traditions."""
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "the-tower", "tradition": "Tarot de Marseille"})
    assert "error" in result
