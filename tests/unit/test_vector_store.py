"""Unit tests for ChromaVectorStore (T13): add/query/delete against a real
embedded Chroma instance, using fake (hand-built) embeddings — no Ollama needed."""

from pathlib import Path

import pytest

from mythrix.core.vector.chunking import Chunk
from mythrix.core.vector.store import ChromaVectorStore, ChunkMetadata


@pytest.fixture
def store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(tmp_path / "chroma")


def _metadata(*, source_id: str, tradition_slug: str, domain: str = "tarot") -> ChunkMetadata:
    return ChunkMetadata(
        source_id=source_id,
        tradition_slug=tradition_slug,
        domain=domain,
        embedding_model="fake-embed",
        ingested_at="2026-01-01T00:00:00+00:00",
    )


def test_add_and_similarity_search_scoped_to_tradition(store: ChromaVectorStore) -> None:
    tower_chunk = Chunk(index=0, text="The Tower depicts sudden upheaval.", char_start=0, char_end=35)
    fool_chunk = Chunk(index=0, text="The Fool walks toward a cliff.", char_start=0, char_end=31)

    store.add_chunks(
        [tower_chunk], embeddings=[[1.0, 0.0]], metadata=_metadata(source_id="waite", tradition_slug="rider-waite")
    )
    store.add_chunks(
        [fool_chunk], embeddings=[[0.0, 1.0]], metadata=_metadata(source_id="crowley", tradition_slug="other-tradition")
    )

    hits = store.similarity_search([1.0, 0.0], tradition_slug="rider-waite", top_k=5)

    assert len(hits) == 1
    assert hits[0].text == "The Tower depicts sudden upheaval."
    assert hits[0].source_id == "waite"
    assert hits[0].tradition_slug == "rider-waite"
    assert hits[0].chunk_index == 0
    assert hits[0].char_start == 0
    assert hits[0].char_end == 35
    assert hits[0].embedding_model == "fake-embed"


def test_similarity_search_respects_top_k(store: ChromaVectorStore) -> None:
    chunks = [Chunk(index=i, text=f"chunk {i}", char_start=0, char_end=7) for i in range(5)]
    embeddings = [[float(i), 0.0] for i in range(5)]
    store.add_chunks(chunks, embeddings=embeddings, metadata=_metadata(source_id="s1", tradition_slug="t1"))

    hits = store.similarity_search([0.0, 0.0], tradition_slug="t1", top_k=2)

    assert len(hits) == 2


def test_delete_by_source_removes_only_that_sources_chunks(store: ChromaVectorStore) -> None:
    chunk_a = Chunk(index=0, text="from source a", char_start=0, char_end=13)
    chunk_b = Chunk(index=0, text="from source b", char_start=0, char_end=13)
    store.add_chunks([chunk_a], embeddings=[[1.0, 0.0]], metadata=_metadata(source_id="a", tradition_slug="t1"))
    store.add_chunks([chunk_b], embeddings=[[0.0, 1.0]], metadata=_metadata(source_id="b", tradition_slug="t1"))

    store.delete_by_source("a")

    assert store.count() == 1
    remaining = store.similarity_search([0.0, 1.0], tradition_slug="t1", top_k=5)
    assert len(remaining) == 1
    assert remaining[0].source_id == "b"


def test_add_chunks_is_upsert_idempotent(store: ChromaVectorStore) -> None:
    chunk = Chunk(index=0, text="original text", char_start=0, char_end=13)
    metadata = _metadata(source_id="s1", tradition_slug="t1")

    store.add_chunks([chunk], embeddings=[[1.0, 0.0]], metadata=metadata)
    store.add_chunks([chunk], embeddings=[[1.0, 0.0]], metadata=metadata)

    assert store.count() == 1


def test_mismatched_chunk_and_embedding_counts_raises(store: ChromaVectorStore) -> None:
    chunk = Chunk(index=0, text="text", char_start=0, char_end=4)
    with pytest.raises(ValueError, match="chunks"):
        store.add_chunks([chunk], embeddings=[], metadata=_metadata(source_id="s1", tradition_slug="t1"))


def test_chunk_locator_round_trips_through_a_hit(store: ChromaVectorStore) -> None:
    chunk = Chunk(index=0, text="Isaac is born.", char_start=0, char_end=14, locator="Genesis 21")
    store.add_chunks([chunk], embeddings=[[1.0, 0.0]], metadata=_metadata(source_id="s1", tradition_slug="t1"))

    hits = store.similarity_search([1.0, 0.0], tradition_slug="t1", top_k=5)

    assert hits[0].locator == "Genesis 21"


def test_document_contains_filters_to_chunks_with_that_literal_text(store: ChromaVectorStore) -> None:
    """An exact-value fact (e.g. gematria) needs a literal-text match, not a
    fuzzy semantic one — `document_contains` combines both: only chunks
    containing the substring are candidates, ranked among those by embedding
    similarity (pipeline.py's module docstring)."""
    matching = Chunk(index=0, text="he was a hundred years old", char_start=0, char_end=26)
    non_matching = Chunk(index=1, text="he was a young man", char_start=27, char_end=45)
    store.add_chunks(
        [matching, non_matching],
        embeddings=[[1.0, 0.0], [1.0, 0.0]],
        metadata=_metadata(source_id="s1", tradition_slug="t1"),
    )

    hits = store.similarity_search([1.0, 0.0], tradition_slug="t1", top_k=5, document_contains="hundred")

    assert len(hits) == 1
    assert hits[0].text == "he was a hundred years old"
