"""Unit tests for `run_query` (T20, reduced by T38): called directly with
fakes/fixtures, no Typer/subprocess machinery and no running Ollama needed.
Every query is now facts-only in shape (FR29 — no generation model is ever
constructed on this path), so there is no `synthesizer_factory`/`strict`
surface left to test here; `test_formatting.py` covers the pair-groups
rendering these tests exercise end-to-end."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mythrix.cli.commands.query import run_query
from mythrix.core.errors import ModelUnavailableError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import Attribute, Citation, Interpretation, Source, Symbol, Tradition
from mythrix.core.vector.chunking import Chunk
from mythrix.core.vector.store import ChromaVectorStore, ChunkMetadata

RIDER_WAITE = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")


class FakeEmbedder:
    model_name = "fake-embed"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


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


def _run(**overrides) -> int:  # noqa: ANN003
    defaults = {"top_k": 6, "match_pool_size": 30, "merge_top_k": 6, "min_score": 0.0}
    defaults.update(overrides)
    return run_query(**defaults)


def test_query_succeeds_and_never_constructs_a_generation_model(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    """FR29: the query path invokes no generation model at all — there is no
    `synthesizer_factory` parameter left for a test to fail-fast on, which is
    itself the structural proof."""
    exit_code = _run(
        symbol="the-tower",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "GRAPH FACTS" in output
    assert "[G1]" in output


def test_unreachable_embedder_is_a_clean_error_not_a_traceback(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    """Retrieval embeds the query text even though nothing generates text
    afterward — an unreachable embedder must still surface as a clean
    `MythrixError`, not an unhandled traceback."""

    class UnreachableEmbedder:
        model_name = "nomic-embed-text"

        def embed(self, texts: list[str]) -> list[list[float]]:
            raise ModelUnavailableError(self.model_name)

    exit_code = _run(
        symbol="the-tower",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=UnreachableEmbedder(),
    )

    assert exit_code == 1
    assert "Error" in capsys.readouterr().err


def test_unknown_symbol_returns_nonzero_exit(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = _run(
        symbol="nonexistent",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
    )

    assert exit_code == 1
    assert "Error" in capsys.readouterr().err


def test_json_output_includes_pair_candidates_key(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    """FR16, FR27: `--json` output carries the pair-convergence evidence
    alongside per-concept candidates, even when empty."""
    exit_code = _run(
        symbol="the-tower",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
        as_json=True,
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"pair_candidates"' in output
    assert '"concept_candidates"' in output


def test_query_surfaces_a_concept_pair_convergence(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    """End-to-end through the real Chroma store: a passage retrieved for
    both an attribute's concept and a keyword concept converges into a pair
    group in the rendered output (FR27)."""
    the_tower = graph_store.get_interpretation("the-tower", "rider-waite").symbol
    updated_interpretation = graph_store.get_interpretation("the-tower", "rider-waite").interpretation.model_copy(
        update={
            "attributes": (
                Attribute(id="attr-element", key="element", value="Fire"),
                Attribute(id="attr-keyword", key="keyword", value="upheaval"),
            )
        }
    )
    graph_store.upsert_symbol_with_interpretation(the_tower, updated_interpretation)

    embedding = [1.0, 0.0]
    vector_store.add_chunks(
        [Chunk(index=0, text="Fire brings sudden upheaval to The Tower.", char_start=0, char_end=41)],
        [embedding],
        ChunkMetadata(
            source_id="waite",
            tradition_slug="rider-waite",
            domain="tarot",
            embedding_model="fake-embed",
            ingested_at="2026-01-01T00:00:00Z",
        ),
    )

    exit_code = _run(
        symbol="the-tower",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "CANDIDATES — [" in output
