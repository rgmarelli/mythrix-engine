"""Unit tests for T20's `run_query` — called directly with fakes/fixtures, no
Typer/subprocess machinery and no running Ollama needed."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mythrix.cli.commands.query import run_query
from mythrix.core.errors import ModelUnavailableError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import Attribute, Citation, Interpretation, InterpretationResult, Source, Symbol, Tradition
from mythrix.core.synthesis.citations import validate_citations
from mythrix.core.vector.store import ChromaVectorStore

RIDER_WAITE = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")


class FakeEmbedder:
    model_name = "fake-embed"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class FakeSynthesizer:
    generation_model = "fake-model"

    def __init__(self, narrative: str) -> None:
        self._narrative = narrative

    def synthesize(self, context):  # noqa: ANN001, ANN201
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


@pytest.fixture
def graph_store(tmp_path: Path) -> KuzuGraphStore:
    store = KuzuGraphStore(tmp_path / "graph.kuzu")
    store.upsert_tradition(RIDER_WAITE)
    store.upsert_source(Source(id="waite", title="The Pictorial Key to the Tarot", author="A. E. Waite"))
    the_tower = Symbol(id="the-tower", slug="the-tower", canonical_name="The Tower", symbol_type="major-arcana")
    interpretation = Interpretation(
        id="the-tower::rider-waite",
        symbol_id="the-tower",
        tradition=RIDER_WAITE,
        display_name="The Tower",
        summary="Sudden upheaval; the collapse of false structures.",
        attributes=(Attribute(id="attr-element", key="element", value="Fire"),),
        citations=(Citation(source=Source(id="waite", title="The Pictorial Key to the Tarot", author="A. E. Waite")),),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store.upsert_symbol_with_interpretation(the_tower, interpretation)
    return store


@pytest.fixture
def vector_store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(tmp_path / "chroma")


def test_facts_only_query_succeeds_without_any_synthesizer(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_factory():  # noqa: ANN202
        raise AssertionError("synthesizer_factory must not be called in facts-only mode")

    exit_code = run_query(
        symbol="the-tower",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
        synthesizer_factory=fail_factory,
        top_k=6,
        min_score=0.0,
        facts_only=True,
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "GRAPH FACTS" in output
    assert "[G1]" in output


def test_facts_only_with_unreachable_embedder_is_a_clean_error_not_a_traceback(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression test: retrieval (used even in facts-only mode, to embed the
    query text) must go through the same MythrixError handling as synthesis —
    an unreachable embedder previously escaped as an unhandled traceback."""

    class UnreachableEmbedder:
        model_name = "nomic-embed-text"

        def embed(self, texts: list[str]) -> list[list[float]]:
            raise ModelUnavailableError(self.model_name)

    def fail_factory():  # noqa: ANN202
        raise AssertionError("synthesizer_factory must not be called in facts-only mode")

    exit_code = run_query(
        symbol="the-tower",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=UnreachableEmbedder(),
        synthesizer_factory=fail_factory,
        top_k=6,
        min_score=0.0,
        facts_only=True,
    )

    assert exit_code == 1
    assert "Error" in capsys.readouterr().err


def test_unknown_symbol_returns_nonzero_exit(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = run_query(
        symbol="nonexistent",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
        synthesizer_factory=lambda: FakeSynthesizer("n/a"),
        top_k=6,
        min_score=0.0,
    )

    assert exit_code == 1
    assert "Error" in capsys.readouterr().err


def test_valid_synthesis_returns_zero_exit(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = run_query(
        symbol="the-tower",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
        synthesizer_factory=lambda: FakeSynthesizer("The Tower [G1] represents sudden upheaval."),
        top_k=6,
        min_score=0.0,
    )

    assert exit_code == 0
    assert "represents sudden upheaval" in capsys.readouterr().out


def test_strict_mode_with_fabricated_citation_returns_nonzero_exit(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    narrative = "The Tower [G1] relates to a passage [S9] that was never retrieved."

    exit_code = run_query(
        symbol="the-tower",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
        synthesizer_factory=lambda: FakeSynthesizer(narrative),
        top_k=6,
        min_score=0.0,
        strict=True,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert narrative in captured.out  # the (invalid) result is still shown to the researcher
    assert "S9" in captured.err


def test_non_strict_mode_with_fabricated_citation_still_returns_zero_exit(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    narrative = "The Tower [G1] relates to a passage [S9] that was never retrieved."

    exit_code = run_query(
        symbol="the-tower",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
        synthesizer_factory=lambda: FakeSynthesizer(narrative),
        top_k=6,
        min_score=0.0,
        strict=False,
    )

    assert exit_code == 0
