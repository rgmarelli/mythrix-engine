"""Unit tests for `core/query_service.py`: `execute_query` (the CLI's
retrieval logic, extracted) and `query_fragments` (the API's fragment-centric
form). Real `KuzuGraphStore`/`ChromaVectorStore` against `tmp_path`, a fake
embedder — no running Ollama needed, mirroring `tests/unit/test_cli_query.py`."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mythrix.core.errors import SignNotFoundError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import (
    FragmentQueryResult,
    Interpretant,
    Manifestation,
    RetrievalContext,
    Sign,
    Source,
    Tradition,
)
from mythrix.core.query_service import execute_query, query_fragments
from mythrix.core.vector.store import ChromaVectorStore

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
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store.upsert_sign_with_manifestation(the_tower, manifestation)
    return store


@pytest.fixture
def vector_store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(tmp_path / "chroma")


def _kwargs(**overrides) -> dict:  # noqa: ANN003
    defaults = {"top_k": 6, "match_pool_size": 30, "merge_top_k": 6, "min_score": 0.0}
    defaults.update(overrides)
    return defaults


def test_execute_query_returns_a_retrieval_context(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    context = execute_query(
        symbol="the-tower",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
        **_kwargs(),
    )
    assert isinstance(context, RetrievalContext)
    assert context.graph_facts.sign.slug == "the-tower"


def test_execute_query_propagates_mythrix_error(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    with pytest.raises(SignNotFoundError):
        execute_query(
            symbol="nonexistent",
            tradition="rider-waite",
            graph_store=graph_store,
            vector_store=vector_store,
            embedder=FakeEmbedder(),
            **_kwargs(),
        )


def test_query_fragments_returns_a_fragment_query_result(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    result = query_fragments(
        symbol="the-tower",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
        **_kwargs(),
    )
    assert isinstance(result, FragmentQueryResult)
    assert result.fragments == ()
    assert result.facets.sources == ()
    assert result.facets.interpretants == ()


def test_query_fragments_propagates_mythrix_error(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    with pytest.raises(SignNotFoundError):
        query_fragments(
            symbol="nonexistent",
            tradition="rider-waite",
            graph_store=graph_store,
            vector_store=vector_store,
            embedder=FakeEmbedder(),
            **_kwargs(),
        )
