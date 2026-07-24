"""Unit tests for context rendering (T16, reduced by T37): the marker
enumeration and block renderers `cli/formatting.py` depends on today, and
that a future conversational agent loop would reuse. The concept/general
prompt-assembly functions this file used to test are retired along with
concept-scoped synthesis (FR25, FR-RT-10) — see `synthesis/prompts.py`'s module
docstring.
"""

from datetime import UTC, datetime

from mythrix.core.models import (
    Citation,
    GraphFacts,
    Interpretant,
    IntersemioticInterpretant,
    Manifestation,
    RetrievedPassage,
    Sign,
    Source,
    Tradition,
)
from mythrix.core.synthesis.prompts import graph_fact_ids, passage_ids, render_passages_block

RIDER_WAITE = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")
GOLDEN_DAWN = Tradition(
    id="golden-dawn-kabbalah", slug="golden-dawn-kabbalah", name="Golden Dawn Kabbalah", domain="kabbalah"
)
PEH = Sign(
    id="hebrew-letter-peh",
    slug="hebrew-letter-peh",
    canonical_name="Peh",
    sign_type="hebrew-letter",
    semiotic_system="hebrew_alef_bet",
)
WAITE_SOURCE = Source(
    id="waite-pictorial-key", domain="tarot", title="The Pictorial Key to the Tarot", author="A. E. Waite"
)

THE_TOWER = Sign(
    id="the-tower",
    slug="the-tower",
    canonical_name="The Tower",
    sign_type="major-arcana",
    semiotic_system="tarot",
    intersemiotic_interpretants=(
        IntersemioticInterpretant(relationship="corresponds_to_letter", target_sign=PEH, according_to=GOLDEN_DAWN),
    ),
)
THE_TOWER_MANIFESTATION = Manifestation(
    id="the-tower::rider-waite",
    sign_id="the-tower",
    tradition=RIDER_WAITE,
    display_name="The Tower",
    denotation="Sudden upheaval; the collapse of false structures.",
    interpretants=(Interpretant(id="interp-element", type="element", value="Fire"),),
    citations=(Citation(source=WAITE_SOURCE, locator="p. 143"),),
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
)
GRAPH_FACTS = GraphFacts(sign=THE_TOWER, manifestation=THE_TOWER_MANIFESTATION)
PASSAGE = RetrievedPassage(
    chunk_id="waite-pictorial-key::0",
    source=WAITE_SOURCE,
    text="Sudden upheaval; the collapse of false structures.",
    locator="p. 143",
    score=0.9,
)


def test_graph_fact_ids_enumerates_identity_interpretant_and_correspondence() -> None:
    # 1 identity line + 1 interpretant + 1 correspondence = G1..G3
    assert graph_fact_ids(GRAPH_FACTS) == ("G1", "G2", "G3")


def test_passage_ids_enumerates_passages() -> None:
    assert passage_ids((PASSAGE, PASSAGE)) == ("S1", "S2")


def test_render_passages_block_includes_verbatim_text_and_attribution() -> None:
    block = render_passages_block((PASSAGE,))

    assert "[S1]" in block
    assert "Sudden upheaval; the collapse of false structures." in block
    assert "The Pictorial Key to the Tarot" in block
    assert "A. E. Waite" in block
    assert "p. 143" in block


def test_render_passages_block_handles_no_passages() -> None:
    block = render_passages_block(())
    assert "none retrieved" in block
