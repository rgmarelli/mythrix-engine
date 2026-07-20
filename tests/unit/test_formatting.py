"""Unit tests for CLI output rendering (T19, reduced by T38): graph facts,
per-concept candidates (FR24), and concept-pair convergence (FR27). The
result renderers this file used to test (`render_result_human`/`_json`) are
retired along with concept-scoped synthesis — every query is now facts-only
in shape (FR29)."""

import json
from datetime import UTC, datetime

from mythrix.cli.formatting import render_facts_human, render_facts_json
from mythrix.core.models import (
    ConceptCandidates,
    ConceptMatchScore,
    ConceptPairCandidates,
    GraphFacts,
    Manifestation,
    MergedCandidate,
    RetrievalContext,
    RetrievedPassage,
    Sign,
    Source,
    Tradition,
)

RIDER_WAITE = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")
THE_TOWER = Sign(
    id="the-tower",
    slug="the-tower",
    canonical_name="The Tower",
    sign_type="major-arcana",
    semiotic_system="tarot",
)
MANIFESTATION = Manifestation(
    id="the-tower::rider-waite",
    sign_id="the-tower",
    tradition=RIDER_WAITE,
    display_name="The Tower",
    denotation="Sudden upheaval; the collapse of false structures.",
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
)
GRAPH_FACTS = GraphFacts(sign=THE_TOWER, manifestation=MANIFESTATION)
PASSAGE = RetrievedPassage(
    chunk_id="waite::0",
    source=Source(id="waite", domain="tarot", title="The Pictorial Key to the Tarot", author="A. E. Waite"),
    text="Catastrophe strikes without warning.",
    locator="p. 143",
    score=0.9,
)
GENESIS_PASSAGE = RetrievedPassage(
    chunk_id="douay::genesis-21-5",
    source=Source(
        id="douay",
        domain="scripture",
        citation_label="Douay-Rheims",
        title="The Holy Bible, Douay-Rheims",
        author="Various",
    ),
    text="And Abraham was a hundred years old, when Isaac his son was born to him.",
    locator="Genesis 21:5",
    score=0.61,
)
CONTEXT = RetrievalContext(
    graph_facts=GRAPH_FACTS, concept_candidates=(ConceptCandidates(concept="element", passages=(PASSAGE,)),)
)


def test_render_facts_human_includes_graph_facts_and_concept_candidates() -> None:
    output = render_facts_human(CONTEXT)

    assert "GRAPH FACTS" in output
    assert "[G1]" in output
    assert 'CANDIDATES — "element"' in output
    assert "[S1]" in output
    assert "Catastrophe strikes without warning." in output


def test_render_facts_human_reports_no_candidates_for_an_empty_context() -> None:
    empty_context = RetrievalContext(graph_facts=GRAPH_FACTS)

    output = render_facts_human(empty_context)

    assert "CANDIDATES\n(none retrieved)" in output


def test_render_facts_json_is_valid_and_grouped_by_concept() -> None:
    payload = json.loads(render_facts_json(CONTEXT))

    assert payload["graph_facts"]["sign"]["canonical_name"] == "The Tower"
    assert payload["graph_facts"]["manifestation"]["tradition_id"] == "rider-waite"
    concept_payload = payload["concept_candidates"]["element"]
    assert concept_payload[0]["text"] == PASSAGE.text
    assert concept_payload[0]["chunk_id"] == "waite::0"
    assert concept_payload[0]["char_start"] == 0
    assert concept_payload[0]["source_id"] == "waite"


def test_render_facts_json_lists_referenced_sources_and_traditions_once() -> None:
    payload = json.loads(render_facts_json(CONTEXT))

    assert payload["sources"]["waite"]["title"] == "The Pictorial Key to the Tarot"
    assert payload["sources"]["waite"]["author"] == "A. E. Waite"
    assert payload["traditions"]["rider-waite"]["name"] == "Rider-Waite-Smith"


def test_render_facts_json_deduplicates_a_source_cited_by_both_a_concept_and_a_pair_candidate() -> None:
    """A source cited by a concept candidate and again by a pair candidate
    appears exactly once in `sources`, not once per citing passage."""
    merged_candidate = MergedCandidate(passage=PASSAGE, matches=(ConceptMatchScore(concept="element", score=0.9),))
    pair = ConceptPairCandidates(concepts=("element", "upheaval"), candidates=(merged_candidate,))
    context = RetrievalContext(
        graph_facts=GRAPH_FACTS,
        concept_candidates=(ConceptCandidates(concept="element", passages=(PASSAGE,)),),
        pair_candidates=(pair,),
    )

    payload = json.loads(render_facts_json(context))

    assert list(payload["sources"].keys()) == ["waite"]
    assert list(payload["traditions"].keys()) == ["rider-waite"]


def test_render_facts_json_includes_an_empty_pair_candidates_list_by_default() -> None:
    payload = json.loads(render_facts_json(CONTEXT))

    assert payload["pair_candidates"] == []


def _context_with_a_pair() -> RetrievalContext:
    merged_candidate = MergedCandidate(
        passage=GENESIS_PASSAGE,
        matches=(
            ConceptMatchScore(concept="laughter", score=0.61),
            ConceptMatchScore(concept="child", score=0.55),
        ),
        combined_score=0.58,
    )
    pair = ConceptPairCandidates(concepts=("laughter", "child"), candidates=(merged_candidate,))
    return RetrievalContext(graph_facts=GRAPH_FACTS, pair_candidates=(pair,))


def test_render_facts_human_includes_a_pair_group_with_combined_and_component_scores() -> None:
    """FR27: a pair group is headed by its members and shows the combined
    score alongside each concept's own component — the verdict and its
    inputs together (see cli/formatting.py)."""
    output = render_facts_human(_context_with_a_pair())

    assert "CANDIDATES — [laughter, child]" in output
    assert "Symbols: laughter, child" in output
    assert "0.58" in output  # combined score
    assert "laughter 0.61" in output
    assert "child 0.55" in output
    assert "And Abraham was a hundred years old" in output
    assert "Genesis 21:5" in output


def test_render_facts_human_attributes_a_passage_by_its_sources_citation_label() -> None:
    """A source with a `citation_label` (every corpus document) is attributed
    by that label, not by `title`/`author` — the label is what's meant to be
    shown for a retrieved passage (FR13)."""
    output = render_facts_human(_context_with_a_pair())

    assert "(Douay-Rheims, Genesis 21:5):" in output
    assert "The Holy Bible, Douay-Rheims, Various" not in output


def test_render_facts_human_falls_back_to_title_author_without_a_citation_label() -> None:
    """A source with no `citation_label` set (today, only ever the case for a
    sign's own citation sources, never ingested into the corpus) still
    attributes by title/author rather than rendering an empty label."""
    output = render_facts_human(CONTEXT)

    assert "(The Pictorial Key to the Tarot, A. E. Waite, p. 143):" in output


def test_render_facts_human_shows_an_exact_value_match_without_a_score() -> None:
    """FR28: an exact-value member (e.g. "100") carries no similarity score —
    it's shown by name alone, not as "100 0.00", which would misrepresent a
    guarantee of containment as a similarity judgment."""
    merged_candidate = MergedCandidate(
        passage=GENESIS_PASSAGE,
        matches=(
            ConceptMatchScore(concept="child", score=0.55),
            ConceptMatchScore(concept="100", score=0.0, exact_value=True),
        ),
        combined_score=0.55,
    )
    pair = ConceptPairCandidates(concepts=("child", "100"), candidates=(merged_candidate,))
    context = RetrievalContext(graph_facts=GRAPH_FACTS, pair_candidates=(pair,))

    output = render_facts_human(context)

    assert "CANDIDATES — [child, 100]" in output
    assert "child 0.55" in output
    assert "0.55  (child 0.55 · 100)" in output


def test_render_facts_json_includes_pair_candidates_with_matches_and_passage() -> None:
    payload = json.loads(render_facts_json(_context_with_a_pair()))

    pairs = payload["pair_candidates"]
    assert len(pairs) == 1
    assert pairs[0]["concepts"] == ["laughter", "child"]
    candidate = pairs[0]["candidates"][0]
    assert candidate["combined_score"] == 0.58
    assert {m["concept"] for m in candidate["matches"]} == {"laughter", "child"}
    assert all(m["exact_value"] is False for m in candidate["matches"])
    assert candidate["passage"]["chunk_id"] == "douay::genesis-21-5"
    assert candidate["passage"]["source_id"] == "douay"
    assert payload["sources"]["douay"]["title"] == "The Holy Bible, Douay-Rheims"
    assert payload["sources"]["douay"]["citation_label"] == "Douay-Rheims"


def test_render_facts_human_reports_no_pair_candidates_for_an_empty_pair() -> None:
    pair = ConceptPairCandidates(concepts=("laughter", "child"))
    context = RetrievalContext(graph_facts=GRAPH_FACTS, pair_candidates=(pair,))

    output = render_facts_human(context)

    assert "CANDIDATES — [laughter, child]\n(none retrieved)" in output
