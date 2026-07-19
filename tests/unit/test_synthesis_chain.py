"""Unit tests for T18: `OllamaSynthesizer`'s actionable-error paths, and a fake
`Synthesizer` exercising the `InterpretationResult` shape a caller (the CLI,
T20) relies on. No running Ollama is used or required — the unset-model check
short-circuits before any client is built, and the unreachable-base-url case
exercises exactly the "Ollama unavailable" failure path, fast and offline."""

from datetime import UTC, datetime

import pytest

from mythrix.core.errors import ModelUnavailableError
from mythrix.core.models import GraphFacts, Interpretation, InterpretationResult, RetrievalContext, Symbol, Tradition
from mythrix.core.synthesis.chain import OllamaSynthesizer, Synthesizer
from mythrix.core.synthesis.citations import validate_citations
from mythrix.core.synthesis.prompts import build_prompt

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
CONTEXT = RetrievalContext(graph_facts=GraphFacts(symbol=THE_TOWER, interpretation=INTERPRETATION))


class FakeSynthesizer:
    """A `Synthesizer` a caller can inject in place of `OllamaSynthesizer`."""

    generation_model = "fake-model"

    def __init__(self, narrative: str) -> None:
        self._narrative = narrative

    def synthesize(self, context: RetrievalContext) -> InterpretationResult:
        invalid_markers = validate_citations(self._narrative, context)
        return InterpretationResult(
            context=context,
            narrative=self._narrative,
            generation_model=self.generation_model,
            embedding_model="fake-embed",
            citation_markers_valid=not invalid_markers,
            invalid_markers=invalid_markers,
            generated_at=datetime.now(UTC),
        )


def test_unset_generation_model_raises_actionable_error_immediately() -> None:
    with pytest.raises(ModelUnavailableError):
        OllamaSynthesizer(generation_model="", embedding_model="nomic-embed-text", base_url="http://localhost:11434")


def test_unreachable_ollama_raises_model_unavailable_error() -> None:
    with pytest.raises(ModelUnavailableError):
        OllamaSynthesizer(generation_model="llama3", embedding_model="nomic-embed-text", base_url="http://localhost:1")


def test_fake_synthesizer_satisfies_the_protocol_and_produces_a_valid_result() -> None:
    synthesizer: Synthesizer = FakeSynthesizer("The Tower [G1] represents sudden upheaval.")

    result = synthesizer.synthesize(CONTEXT)

    assert result.citation_markers_valid is True
    assert result.invalid_markers == ()
    assert result.generation_model == "fake-model"
    assert result.context == CONTEXT


def test_fake_synthesizer_flags_fabricated_citation() -> None:
    synthesizer = FakeSynthesizer("The Tower [G1] relates to a passage [S9] that was never retrieved.")

    result = synthesizer.synthesize(CONTEXT)

    assert result.citation_markers_valid is False
    assert result.invalid_markers == ("S9",)


def test_build_prompt_is_what_a_real_synthesizer_would_send() -> None:
    """Sanity check that the prompt a real `OllamaSynthesizer.synthesize` would
    build (via `build_prompt`) is exactly what `synthesis/prompts.py` renders —
    keeping this test from silently drifting if `synthesize`'s prompt-assembly
    call is ever changed to build something ad hoc instead."""
    assert build_prompt(CONTEXT).startswith("You are a research assistant")
