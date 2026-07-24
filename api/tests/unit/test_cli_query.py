"""Unit tests for `run_query` (T20, reduced by T38): called directly with
fakes/fixtures, no Typer/subprocess machinery and no running Ollama needed.
Every query is now facts-only in shape (FR-RT-10 — no generation model is ever
constructed on this path), so there is no `synthesizer_factory`/`strict`
surface left to test here; `test_formatting.py` covers the pair-groups
rendering these tests exercise end-to-end."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mythrix.cli.commands.query import run_query
from mythrix.core.errors import ModelUnavailableError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import Citation, Interpretant, Manifestation, Sign, Source, Tradition
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
    store.upsert_source(
        Source(id="waite", domain="tarot", title="The Pictorial Key to the Tarot", author="A. E. Waite")
    )
    the_tower = Sign(
        id="the-tower",
        slug="the-tower",
        canonical_name="The Tower",
        sign_type="major-arcana",
        semiotic_system="tarot",
    )
    manifestation = Manifestation(
        id="the-tower::rider-waite",
        sign_id="the-tower",
        tradition=RIDER_WAITE,
        display_name="The Tower",
        denotation="Sudden upheaval; the collapse of false structures.",
        interpretants=(Interpretant(id="interp-element", type="element", value="Fire"),),
        citations=(
            Citation(
                source=Source(id="waite", domain="tarot", title="The Pictorial Key to the Tarot", author="A. E. Waite")
            ),
        ),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store.upsert_sign_with_manifestation(the_tower, manifestation)
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
    """FR-RT-10: the query path invokes no generation model at all — there is no
    `synthesizer_factory` parameter left for a test to fail-fast on, which is
    itself the structural proof."""
    exit_code = _run(
        sign="the-tower",
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
        sign="the-tower",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=UnreachableEmbedder(),
    )

    assert exit_code == 1
    assert "Error" in capsys.readouterr().err


def test_unknown_sign_returns_nonzero_exit(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = _run(
        sign="nonexistent",
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
    """FR-RT-06, FR-RT-08: `--json` output carries the pair-convergence evidence
    alongside per-concept candidates, even when empty."""
    exit_code = _run(
        sign="the-tower",
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
    both an interpretant's concept and a keyword concept converges into a
    pair group in the rendered output (FR-RT-08)."""
    the_tower = graph_store.get_manifestation("the-tower", "rider-waite").sign
    updated_manifestation = graph_store.get_manifestation("the-tower", "rider-waite").manifestation.model_copy(
        update={
            "interpretants": (
                Interpretant(id="interp-element", type="element", value="Fire"),
                Interpretant(id="interp-keyword", type="concept", value="upheaval"),
            )
        }
    )
    graph_store.upsert_sign_with_manifestation(the_tower, updated_manifestation)

    embedding = [1.0, 0.0]
    vector_store.add_chunks(
        [Chunk(index=0, text="Fire brings sudden upheaval to The Tower.", char_start=0, char_end=41)],
        [embedding],
        ChunkMetadata(
            source_id="waite",
            domain="tarot",
            embedding_model="fake-embed",
            ingested_at="2026-01-01T00:00:00Z",
        ),
    )

    exit_code = _run(
        sign="the-tower",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "CANDIDATES — [" in output
