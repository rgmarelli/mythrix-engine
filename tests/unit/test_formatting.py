"""Unit tests for CLI output rendering (T19)."""

import json
from datetime import UTC, datetime

from mythrix.cli.formatting import render_facts_human, render_facts_json, render_result_human, render_result_json
from mythrix.core.models import (
    GraphFacts,
    Interpretation,
    InterpretationResult,
    RetrievalContext,
    RetrievedPassage,
    Source,
    Symbol,
    Tradition,
)

RIDER_WAITE = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")
THE_TOWER = Symbol(id="the-tower", slug="the-tower", canonical_name="The Tower", symbol_type="major-arcana")
INTERPRETATION = Interpretation(
    id="the-tower::rider-waite",
    symbol_id="the-tower",
    tradition=RIDER_WAITE,
    display_name="The Tower",
    summary="Sudden upheaval; the collapse of false structures.",
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
)
GRAPH_FACTS = GraphFacts(symbol=THE_TOWER, interpretation=INTERPRETATION)
PASSAGE = RetrievedPassage(
    chunk_id="waite::0",
    source=Source(id="waite", title="The Pictorial Key to the Tarot", author="A. E. Waite"),
    tradition=RIDER_WAITE,
    text="Sudden upheaval; the collapse of false structures.",
    locator="p. 143",
    score=0.9,
)
CONTEXT = RetrievalContext(graph_facts=GRAPH_FACTS, passages=(PASSAGE,))
RESULT = InterpretationResult(
    context=CONTEXT,
    narrative="The Tower [G1] represents sudden upheaval, per the source [S1].",
    generation_model="llama3.2",
    embedding_model="nomic-embed-text",
    citation_markers_valid=True,
    generated_at=datetime(2026, 1, 2, tzinfo=UTC),
)


def test_render_facts_human_includes_graph_facts_and_passages() -> None:
    output = render_facts_human(CONTEXT)

    assert "GRAPH FACTS" in output
    assert "[G1]" in output
    assert "PASSAGES" in output
    assert "[S1]" in output
    assert "Sudden upheaval; the collapse of false structures." in output


def test_render_facts_json_is_valid_and_contains_markers_and_raw_fields() -> None:
    payload = json.loads(render_facts_json(CONTEXT))

    assert payload["graph_facts"]["markers"]["G1"]
    assert payload["passages"]["markers"]["S1"] == PASSAGE.text
    assert payload["passages"]["items"][0]["chunk_id"] == "waite::0"
    assert payload["passages"]["items"][0]["char_start"] == 0


def test_render_result_human_includes_narrative_references_and_model_info() -> None:
    output = render_result_human(RESULT)

    assert "The Tower [G1] represents sudden upheaval, per the source [S1]." in output
    assert "References:" in output
    assert "Sudden upheaval; the collapse of false structures." in output
    assert "A. E. Waite" in output
    assert "p. 143" in output
    assert "llama3.2" in output
    assert "nomic-embed-text" in output
    assert "2026-01-02" in output
    assert "Citations valid: yes" in output


def test_render_result_human_flags_invalid_citations() -> None:
    invalid_result = RESULT.model_copy(update={"citation_markers_valid": False, "invalid_markers": ("S9",)})

    output = render_result_human(invalid_result)

    assert "Citations valid: NO" in output
    assert "S9" in output


def test_render_result_json_contains_full_evidentiary_chain() -> None:
    payload = json.loads(render_result_json(RESULT))

    assert payload["narrative"] == RESULT.narrative
    assert payload["generation_model"] == "llama3.2"
    assert payload["embedding_model"] == "nomic-embed-text"
    assert payload["citation_markers_valid"] is True
    assert payload["invalid_markers"] == []
    assert payload["generated_at"] == "2026-01-02T00:00:00+00:00"
    assert payload["graph_facts"]["markers"]["G1"]
    assert payload["passages"]["items"][0]["text"] == PASSAGE.text
