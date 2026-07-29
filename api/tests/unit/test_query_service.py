# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `core/query_service.py`. Real
`KuzuGraphStore`/`ChromaVectorStore` against `tmp_path`, a fake embedder — no
running Ollama needed."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mythrix.core.errors import AdhocQueryValidationError, SignNotFoundError, SourceNotFoundError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import (
    AdhocTerm,
    Interpretant,
    Manifestation,
    RegionQueryResult,
    Sign,
    Source,
    Tradition,
)
from mythrix.core.query_service import execute_adhoc_query, fetch_source_segments, query_regions
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
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store.upsert_sign_with_manifestation(the_tower, manifestation)
    return store


@pytest.fixture
def vector_store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(tmp_path / "chroma")


def _region_kwargs(**overrides) -> dict:  # noqa: ANN003
    defaults = {
        "match_pool_size": 30,
        "min_score": 0.0,
        "region_window_size": 3,
        "region_min_interpretants": 1,
    }
    defaults.update(overrides)
    return defaults


def test_query_regions_returns_a_region_query_result(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    result = query_regions(
        sign="the-tower",
        tradition="rider-waite",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
        **_region_kwargs(),
    )
    assert isinstance(result, RegionQueryResult)
    assert result.regions == ()
    assert result.facets.sources == ()
    assert result.facets.interpretants == ()


def test_query_regions_propagates_mythrix_error(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    with pytest.raises(SignNotFoundError):
        query_regions(
            sign="nonexistent",
            tradition="rider-waite",
            graph_store=graph_store,
            vector_store=vector_store,
            embedder=FakeEmbedder(),
            **_region_kwargs(),
        )


@pytest.fixture
def bare_graph_store(tmp_path: Path) -> KuzuGraphStore:
    """A graph store with a `Source` (for citation hydration) but no `Sign`
    or `Manifestation` at all — proves `execute_adhoc_query` never touches
    the Sign Graph (`specs/interfaces/agnostic-query.md` FR-AQ-10)."""
    store = KuzuGraphStore(tmp_path / "graph.kuzu")
    store.upsert_source(
        Source(id="waite", domain="tarot", title="The Pictorial Key to the Tarot", author="A. E. Waite")
    )
    return store


def test_execute_adhoc_query_needs_no_sign_in_the_graph_store(
    bare_graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    chunks = [
        Chunk(
            index=0,
            text="There were a hundred fish under pisces, full of laughter.",
            char_start=0,
            char_end=10,
            ordinal=0,
            section="",
        )
    ]
    vector_store.add_chunks(
        chunks,
        embeddings=[[1.0, 0.0]],
        metadata=ChunkMetadata(
            source_id="waite", domain="tarot", embedding_model="fake-embed", ingested_at="2026-01-01T00:00:00+00:00"
        ),
    )

    result = execute_adhoc_query(
        terms=[
            AdhocTerm(value="laughter"),
            AdhocTerm(value="hundred", directive="exact"),
            AdhocTerm(value="pisces", directive="filter"),
        ],
        graph_store=bare_graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
        **_region_kwargs(),
    )

    assert isinstance(result, RegionQueryResult)
    assert len(result.regions) == 1
    kinds = {match.interpretant: match.kind for match in result.regions[0].matches}
    assert kinds == {"laughter": "concept", "hundred": "exact", "pisces": "filter"}


def test_execute_adhoc_query_empty_terms_raises(
    bare_graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    with pytest.raises(AdhocQueryValidationError):
        execute_adhoc_query(
            terms=[],
            graph_store=bare_graph_store,
            vector_store=vector_store,
            embedder=FakeEmbedder(),
            **_region_kwargs(),
        )


def test_fetch_source_segments_returns_the_ordinal_range(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    chunks = [
        Chunk(index=i, text=f"verse {i}", char_start=0, char_end=7, ordinal=i, section="Genesis 20") for i in range(5)
    ]
    vector_store.add_chunks(
        chunks,
        embeddings=[[1.0, 0.0]] * 5,
        metadata=ChunkMetadata(
            source_id="waite", domain="tarot", embedding_model="fake-embed", ingested_at="2026-01-01T00:00:00+00:00"
        ),
    )

    segments = fetch_source_segments(
        source_id="waite", start_ordinal=1, end_ordinal=3, graph_store=graph_store, vector_store=vector_store
    )

    assert [s.ordinal for s in segments] == [1, 2, 3]
    assert [s.text for s in segments] == ["verse 1", "verse 2", "verse 3"]
    assert all(s.section == "Genesis 20" for s in segments)


def test_fetch_source_segments_unknown_source_raises(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    with pytest.raises(SourceNotFoundError):
        fetch_source_segments(
            source_id="nonexistent", start_ordinal=0, end_ordinal=1, graph_store=graph_store, vector_store=vector_store
        )
