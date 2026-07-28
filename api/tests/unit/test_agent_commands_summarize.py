"""Unit tests for `agent/commands/summarize.py`: `/summarize` detection, focus/
concept resolution, and hotspot-coordinate parsing (specs/interfaces/agent.md
FR-AG-33–FR-AG-36). Pure functions — nothing here touches a store, a graph, or
a model."""

import pytest

from mythrix.agent.commands.summarize import (
    SUMMARIZE_COMMAND,
    command_of,
    concepts_for,
    focus_of,
    resolve_hotspot,
)


def test_command_of_matches_the_whole_head_token() -> None:
    """A `startswith` test would read `/summarized` as `/summarize`."""
    assert command_of(SUMMARIZE_COMMAND) == SUMMARIZE_COMMAND
    assert command_of("/summarize focus on redemption imagery") == SUMMARIZE_COMMAND
    assert command_of("/SUMMARIZE") == SUMMARIZE_COMMAND
    assert command_of("/summarized") is None
    assert command_of("summarize this") is None
    assert command_of("/query laughter") is None


def test_focus_of_extracts_trailing_text() -> None:
    assert focus_of("/summarize focus on redemption imagery") == "focus on redemption imagery"
    assert focus_of("/summarize") == ""
    assert focus_of("/summarize   ") == ""
    assert focus_of("/summarize  extra   spacing  ") == "extra   spacing"


def test_concepts_for_prefers_focus_over_interpretant() -> None:
    assert concepts_for("redemption imagery", "fire") == ["redemption imagery"]


def test_concepts_for_falls_back_to_interpretant() -> None:
    assert concepts_for("", "fire") == ["fire"]


def test_concepts_for_falls_back_to_no_scoping_concept() -> None:
    assert concepts_for("", None) == []


def test_resolve_hotspot_parses_source_id_and_ordinal_range() -> None:
    assert resolve_hotspot("waite::0-1") == ("waite", 0, 1)


def test_resolve_hotspot_raises_on_a_malformed_region_id() -> None:
    with pytest.raises(ValueError, match="region_id"):
        resolve_hotspot("waite-0-1")
