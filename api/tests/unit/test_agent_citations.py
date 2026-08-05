# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `agent/citations.py` — marker extraction and validation over
the `[G#]`/`[S#]`/`[R#]` vocabulary, checked against a caller-supplied
set of valid identifiers, plus the split between what is validated and what
is stripped from a visible reply."""

from mythrix.agent.citations import extract_markers, find_invalid_markers, strip_all_markers, strip_markers


def test_extract_markers_finds_all_distinct_markers_in_order() -> None:
    text = "The Tower [G1] represents upheaval [S1], as also noted [G1] again, per [S2]."
    assert extract_markers(text) == ("G1", "S1", "S2")


def test_extract_markers_ignores_non_marker_bracketed_text() -> None:
    assert extract_markers("See [note 1] for details.") == ()


def test_find_invalid_markers_with_no_invalid_markers_returns_empty() -> None:
    text = "Claim one [G1], claim two [S1]."
    assert find_invalid_markers(text, {"G1", "S1"}) == ()


def test_fabricated_marker_is_flagged_but_valid_ones_are_not() -> None:
    text = "The Tower [G1] represents upheaval [S1], and also relates to something else [S9]."

    assert find_invalid_markers(text, {"G1", "S1"}) == ("S9",)


def test_multiple_fabricated_markers_are_all_flagged() -> None:
    text = "Claim one [G7], claim two [S9], claim three [G1]."

    assert find_invalid_markers(text, {"G1", "S1"}) == ("G7", "S9")


def test_validation_never_widens_beyond_the_ids_it_was_given() -> None:
    """A marker valid for a *different* turn's tool results must still be
    flagged here — validation never widens beyond exactly what was passed."""
    text = "This relates to something else [S2]."

    assert find_invalid_markers(text, {"G1", "S1"}) == ("S2",)


def test_strip_markers_removes_valid_and_invalid_markers_alike() -> None:
    """The agent never shows marker syntax in a visible reply, regardless of
    validation outcome."""
    assert strip_markers("Upheaval [S1] and something fabricated [S9].") == "Upheaval  and something fabricated ."


def test_region_markers_are_validated_like_every_other_kind() -> None:
    text = "Joy recurs [R1][R3], but not here [R9]."

    assert extract_markers(text) == ("R1", "R3", "R9")
    assert find_invalid_markers(text, {"R1", "R3"}) == ("R9",)


def test_region_markers_survive_stripping_while_the_others_do_not() -> None:
    """FR-DS-23: a region marker names a section of the reply itself, so it is
    what the reader follows — unlike a segment marker, which names an item
    inside a tool result the reader never sees."""
    assert strip_markers("Joy recurs [R1] in the passage [S1].") == "Joy recurs [R1] in the passage ."


def test_strip_all_markers_removes_region_markers_too() -> None:
    """For generated text composed *into* a larger reply: its markers were
    emitted against a vocabulary it was never given, so a surviving `[R#]`
    would name a section it knows nothing about (FR-DS-25)."""
    assert strip_all_markers("Sara laughs [S1] here [G2], per [R7].") == "Sara laughs  here , per ."
