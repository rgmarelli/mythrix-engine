"""Real-Ollama coverage for `OllamaSynthesizer` (T18) — opt-in, since it needs a
running local Ollama daemon with the model pulled. Not run as part of the
default `pytest tests/unit` suite; run explicitly with
`pytest tests/integration -m requires_ollama` after `ollama pull llama3.2`
(or point `--generation-model` at whatever's installed locally).
"""

from datetime import UTC, datetime

import pytest

from mythrix.core.models import GraphFacts, Interpretation, RetrievalContext, Symbol, Tradition
from mythrix.core.synthesis.chain import OllamaSynthesizer

GENERATION_MODEL = "llama3.2"

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
CONTEXT = RetrievalContext(graph_facts=GraphFacts(symbol=THE_TOWER, interpretation=INTERPRETATION))


@pytest.mark.requires_ollama
def test_real_synthesizer_produces_a_grounded_cited_narrative() -> None:
    synthesizer = OllamaSynthesizer(
        generation_model=GENERATION_MODEL, embedding_model="nomic-embed-text", base_url="http://localhost:11434"
    )

    result = synthesizer.synthesize(CONTEXT)

    assert result.narrative.strip() != ""
    assert "[G1]" in result.narrative
    assert result.citation_markers_valid
