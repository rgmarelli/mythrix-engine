"""Unit tests for citation-marker extraction and validation (T17)."""

from datetime import UTC, datetime

from mythrix.core.models import (
    GraphFacts,
    Interpretation,
    RetrievalContext,
    RetrievedPassage,
    Source,
    Symbol,
    Tradition,
)
from mythrix.core.synthesis.citations import extract_markers, validate_citations

RIDER_WAITE = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")
THE_TOWER = Symbol(id="the-tower", slug="the-tower", canonical_name="The Tower", symbol_type="major-arcana")
INTERPRETATION = Interpretation(
    id="the-tower::rider-waite",
    symbol_id="the-tower",
    tradition=RIDER_WAITE,
    display_name="The Tower",
    summary="Sudden upheaval.",
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
)
GRAPH_FACTS = GraphFacts(symbol=THE_TOWER, interpretation=INTERPRETATION)
PASSAGE = RetrievedPassage(
    chunk_id="waite::0",
    source=Source(id="waite", title="The Pictorial Key to the Tarot", author="A. E. Waite"),
    tradition=RIDER_WAITE,
    text="Sudden upheaval; the collapse of false structures.",
)
CONTEXT = RetrievalContext(graph_facts=GRAPH_FACTS, passages=(PASSAGE,))  # valid markers: G1, S1


def test_extract_markers_finds_all_distinct_markers_in_order() -> None:
    text = "The Tower [G1] represents upheaval [S1], as also noted [G1] again."
    assert extract_markers(text) == ("G1", "S1")


def test_extract_markers_ignores_non_marker_bracketed_text() -> None:
    assert extract_markers("See [note 1] for details.") == ()


def test_valid_markers_pass_validation() -> None:
    text = "The Tower [G1] represents upheaval, per the source [S1]."
    assert validate_citations(text, CONTEXT) == ()


def test_fabricated_marker_is_flagged_but_valid_ones_are_not() -> None:
    text = "The Tower [G1] represents upheaval [S1], and also relates to something else [S9]."

    invalid = validate_citations(text, CONTEXT)

    assert invalid == ("S9",)


def test_multiple_fabricated_markers_are_all_flagged() -> None:
    text = "Claim one [G7], claim two [S9], claim three [G1]."

    invalid = validate_citations(text, CONTEXT)

    assert invalid == ("G7", "S9")
