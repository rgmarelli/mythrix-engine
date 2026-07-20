"""Unit tests for `core/query_service.py`: `execute_query` (the CLI's
retrieval logic, extracted) and `stream_query` (the API's incremental form).
Real `KuzuGraphStore`/`ChromaVectorStore` against `tmp_path`, a fake embedder
— no running Ollama needed, mirroring `tests/unit/test_cli_query.py`."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mythrix.core.errors import SymbolNotFoundError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import Attribute, Interpretation, RetrievalContext, Source, Symbol, Tradition
from mythrix.core.query_service import execute_query, stream_query
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
    store.upsert_source(Source(id="waite", title="The Pictorial Key to the Tarot", author="A. E. Waite"))
    the_tower = Symbol(id="the-tower", slug="the-tower", canonical_name="The Tower", symbol_type="major-arcana")
    interpretation = Interpretation(
        id="the-tower::rider-waite",
        symbol_id="the-tower",
        tradition=RIDER_WAITE,
        display_name="The Tower",
        summary="Sudden upheaval; the collapse of false structures.",
        attributes=(Attribute(id="attr-element", key="element", value="Fire"),),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store.upsert_symbol_with_interpretation(the_tower, interpretation)
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
    assert context.graph_facts.symbol.slug == "the-tower"


def test_execute_query_propagates_mythrix_error(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    with pytest.raises(SymbolNotFoundError):
        execute_query(
            symbol="nonexistent",
            tradition="rider-waite",
            graph_store=graph_store,
            vector_store=vector_store,
            embedder=FakeEmbedder(),
            **_kwargs(),
        )


def test_stream_query_yields_graph_facts_first_then_concept_candidates(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    events = list(
        stream_query(
            symbol="the-tower",
            tradition="rider-waite",
            graph_store=graph_store,
            vector_store=vector_store,
            embedder=FakeEmbedder(),
            **_kwargs(),
        )
    )
    assert events[0][0] == "graph_facts"
    assert events[0][1]["symbol"]["slug"] == "the-tower"
    assert all(event_type in {"concept_candidates", "pair_candidates"} for event_type, _ in events[1:])


def test_stream_query_raises_before_first_yield_on_unknown_symbol(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    """The graph lookup happens before the generator's first `yield` — a
    caller priming the generator with one `next()` call sees the error there,
    not mid-iteration (this is what lets the API return a normal 404 instead
    of a mid-stream error event)."""
    gen = stream_query(
        symbol="nonexistent",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
        **_kwargs(),
    )
    with pytest.raises(SymbolNotFoundError):
        next(gen)
