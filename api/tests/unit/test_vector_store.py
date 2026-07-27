"""Unit tests for ChromaVectorStore (T13): add/query/delete against a real
embedded Chroma instance, using fake (hand-built) embeddings — no Ollama needed."""

from pathlib import Path

import pytest

from mythrix.core.vector.chunking import Chunk
from mythrix.core.vector.store import ChromaVectorStore, ChunkMetadata


@pytest.fixture
def store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(tmp_path / "chroma")


def _metadata(*, source_id: str, domain: str = "tarot") -> ChunkMetadata:
    return ChunkMetadata(
        source_id=source_id,
        domain=domain,
        embedding_model="fake-embed",
        ingested_at="2026-01-01T00:00:00+00:00",
    )


def test_add_and_similarity_search_across_the_full_corpus(store: ChromaVectorStore) -> None:
    """FR-CO-02: retrieval always searches every ingested document, regardless of
    which source it came from — there is no tradition to scope by, and no
    filter parameter for one."""
    tower_chunk = Chunk(index=0, text="The Tower depicts sudden upheaval.", char_start=0, char_end=35)
    fool_chunk = Chunk(index=0, text="The Fool walks toward a cliff.", char_start=0, char_end=31)

    store.add_chunks([tower_chunk], embeddings=[[1.0, 0.0]], metadata=_metadata(source_id="waite"))
    store.add_chunks([fool_chunk], embeddings=[[0.0, 1.0]], metadata=_metadata(source_id="crowley"))

    hits = store.similarity_search([1.0, 0.0], top_k=5)

    assert len(hits) == 2  # both sources' chunks are candidates
    assert hits[0].text == "The Tower depicts sudden upheaval."
    assert hits[0].source_id == "waite"
    assert hits[0].domain == "tarot"
    assert hits[0].chunk_index == 0
    assert hits[0].char_start == 0
    assert hits[0].char_end == 35
    assert hits[0].embedding_model == "fake-embed"


def test_similarity_search_respects_top_k(store: ChromaVectorStore) -> None:
    chunks = [Chunk(index=i, text=f"chunk {i}", char_start=0, char_end=7) for i in range(5)]
    embeddings = [[float(i), 0.0] for i in range(5)]
    store.add_chunks(chunks, embeddings=embeddings, metadata=_metadata(source_id="s1"))

    hits = store.similarity_search([0.0, 0.0], top_k=2)

    assert len(hits) == 2


def test_delete_by_source_removes_only_that_sources_chunks(store: ChromaVectorStore) -> None:
    chunk_a = Chunk(index=0, text="from source a", char_start=0, char_end=13)
    chunk_b = Chunk(index=0, text="from source b", char_start=0, char_end=13)
    store.add_chunks([chunk_a], embeddings=[[1.0, 0.0]], metadata=_metadata(source_id="a"))
    store.add_chunks([chunk_b], embeddings=[[0.0, 1.0]], metadata=_metadata(source_id="b"))

    store.delete_by_source("a")

    assert store.count() == 1
    remaining = store.similarity_search([0.0, 1.0], top_k=5)
    assert len(remaining) == 1
    assert remaining[0].source_id == "b"


def test_add_chunks_is_upsert_idempotent(store: ChromaVectorStore) -> None:
    chunk = Chunk(index=0, text="original text", char_start=0, char_end=13)
    metadata = _metadata(source_id="s1")

    store.add_chunks([chunk], embeddings=[[1.0, 0.0]], metadata=metadata)
    store.add_chunks([chunk], embeddings=[[1.0, 0.0]], metadata=metadata)

    assert store.count() == 1


def test_add_chunks_batches_upserts_above_the_clients_max_batch_size(store: ChromaVectorStore) -> None:
    """Fine-grained structural segmentation (FR-CO-05) can turn one document into
    tens of thousands of segments — far more than Chroma's own max batch size
    per `upsert()` call. Patched to a small limit here so the test stays fast
    while still exercising the real batching path."""
    store._client.get_max_batch_size = lambda: 2  # type: ignore[method-assign]
    chunks = [Chunk(index=i, text=f"chunk {i}", char_start=0, char_end=7) for i in range(5)]
    embeddings = [[float(i), 0.0] for i in range(5)]

    store.add_chunks(chunks, embeddings=embeddings, metadata=_metadata(source_id="s1"))

    assert store.count() == 5


def test_mismatched_chunk_and_embedding_counts_raises(store: ChromaVectorStore) -> None:
    chunk = Chunk(index=0, text="text", char_start=0, char_end=4)
    with pytest.raises(ValueError, match="chunks"):
        store.add_chunks([chunk], embeddings=[], metadata=_metadata(source_id="s1"))


def test_chunk_locator_round_trips_through_a_hit(store: ChromaVectorStore) -> None:
    chunk = Chunk(index=0, text="Isaac is born.", char_start=0, char_end=14, locator="Genesis 21")
    store.add_chunks([chunk], embeddings=[[1.0, 0.0]], metadata=_metadata(source_id="s1"))

    hits = store.similarity_search([1.0, 0.0], top_k=5)

    assert hits[0].locator == "Genesis 21"


def test_ordinal_and_section_round_trip_through_a_hit(store: ChromaVectorStore) -> None:
    chunk = Chunk(index=0, text="And what is Nun?", char_start=0, char_end=17, ordinal=82, section="83")
    store.add_chunks([chunk], embeddings=[[1.0, 0.0]], metadata=_metadata(source_id="s1"))

    hits = store.similarity_search([1.0, 0.0], top_k=5)

    assert hits[0].ordinal == 82
    assert hits[0].section == "83"


def test_ordinal_and_section_default_when_unset(store: ChromaVectorStore) -> None:
    chunk = Chunk(index=0, text="plain word-count chunk", char_start=0, char_end=23)
    store.add_chunks([chunk], embeddings=[[1.0, 0.0]], metadata=_metadata(source_id="s1"))

    hits = store.similarity_search([1.0, 0.0], top_k=5)

    assert hits[0].ordinal == 0
    assert hits[0].section == ""


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
        metadata=_metadata(source_id="s1"),
    )

    hits = store.similarity_search([1.0, 0.0], top_k=5, document_contains="hundred")

    assert len(hits) == 1
    assert hits[0].text == "he was a hundred years old"


def test_document_contains_is_word_bounded_not_substring(store: ChromaVectorStore) -> None:
    """FR-RT-15: a token must not match inside a larger word or number —
    `50` inside a chunk mentioning only `150` is a false positive a plain
    substring `$contains` would wrongly return."""
    matching = Chunk(index=0, text="he lived for 50 years", char_start=0, char_end=22)
    non_matching = Chunk(index=1, text="the sum was 150 talents", char_start=23, char_end=47)
    store.add_chunks(
        [matching, non_matching],
        embeddings=[[1.0, 0.0], [1.0, 0.0]],
        metadata=_metadata(source_id="s1"),
    )

    hits = store.similarity_search([1.0, 0.0], top_k=5, document_contains="50")

    assert len(hits) == 1
    assert hits[0].text == "he lived for 50 years"


def test_document_contains_still_matches_the_word_within_a_phrase(store: ChromaVectorStore) -> None:
    chunk = Chunk(index=0, text="a hundred years old", char_start=0, char_end=20)
    store.add_chunks([chunk], embeddings=[[1.0, 0.0]], metadata=_metadata(source_id="s1"))

    hits = store.similarity_search([1.0, 0.0], top_k=5, document_contains="hundred")

    assert len(hits) == 1


def test_get_segments_returns_the_ordinal_range_sorted(store: ChromaVectorStore) -> None:
    chunks = [
        Chunk(index=i, text=f"verse {i}", char_start=0, char_end=7, ordinal=i, section="Genesis 20") for i in range(5)
    ]
    store.add_chunks(chunks, embeddings=[[1.0, 0.0]] * 5, metadata=_metadata(source_id="s1"))

    segments = store.get_segments("s1", start_ordinal=1, end_ordinal=3)

    assert [s.ordinal for s in segments] == [1, 2, 3]
    assert [s.text for s in segments] == ["verse 1", "verse 2", "verse 3"]
    assert all(s.section == "Genesis 20" for s in segments)


def test_get_segments_excludes_other_sources(store: ChromaVectorStore) -> None:
    store.add_chunks(
        [Chunk(index=0, text="from s1", char_start=0, char_end=7, ordinal=0)],
        embeddings=[[1.0, 0.0]],
        metadata=_metadata(source_id="s1"),
    )
    store.add_chunks(
        [Chunk(index=0, text="from s2", char_start=0, char_end=7, ordinal=0)],
        embeddings=[[1.0, 0.0]],
        metadata=_metadata(source_id="s2"),
    )

    segments = store.get_segments("s1", start_ordinal=0, end_ordinal=0)

    assert [s.text for s in segments] == ["from s1"]


def test_get_segments_out_of_range_returns_empty(store: ChromaVectorStore) -> None:
    chunk = Chunk(index=0, text="only verse", char_start=0, char_end=10, ordinal=0)
    store.add_chunks([chunk], embeddings=[[1.0, 0.0]], metadata=_metadata(source_id="s1"))

    assert store.get_segments("s1", start_ordinal=5, end_ordinal=10) == []


def test_get_segments_start_after_end_returns_empty_without_querying(store: ChromaVectorStore) -> None:
    chunk = Chunk(index=0, text="only verse", char_start=0, char_end=10, ordinal=0)
    store.add_chunks([chunk], embeddings=[[1.0, 0.0]], metadata=_metadata(source_id="s1"))

    assert store.get_segments("s1", start_ordinal=3, end_ordinal=1) == []


def test_document_matches_returns_every_containing_chunk_with_no_top_k_cap(store: ChromaVectorStore) -> None:
    """An `"exact"`-directive token (FR-EX-01/02) needs every literal
    occurrence, not an ANN-ranked, `top_k`-capped subset — `document_matches`
    is a pure document scan, so it returns all matching chunks regardless of
    how many there are."""
    chunks = [Chunk(index=i, text=f"chunk {i} mentions a hundred years", char_start=0, char_end=30) for i in range(8)]
    unrelated = Chunk(index=8, text="chunk with no mention of the number", char_start=0, char_end=36)
    store.add_chunks([*chunks, unrelated], embeddings=[[1.0, 0.0]] * 9, metadata=_metadata(source_id="s1"))

    hits = store.document_matches("hundred")

    assert len(hits) == 8
    assert {hit.text for hit in hits} == {c.text for c in chunks}


def test_document_matches_is_word_bounded_not_substring(store: ChromaVectorStore) -> None:
    """FR-RT-15: same whole-word-boundary rule as `document_contains` — `50`
    must not match inside `150`."""
    matching = Chunk(index=0, text="he lived for 50 years", char_start=0, char_end=22)
    non_matching = Chunk(index=1, text="the sum was 150 talents", char_start=23, char_end=47)
    store.add_chunks([matching, non_matching], embeddings=[[1.0, 0.0]] * 2, metadata=_metadata(source_id="s1"))

    hits = store.document_matches("50")

    assert [hit.text for hit in hits] == ["he lived for 50 years"]


def test_document_matches_needs_no_embedding_and_still_returns_the_full_segment(store: ChromaVectorStore) -> None:
    """A caller (e.g. `RetrievalPipeline`) can hydrate a full segment/passage
    from a `document_matches` hit — locator, ordinal, section, and text are
    all populated exactly as `similarity_search` would, even though no query
    embedding was ever involved. `distance` is a placeholder (`0.0`), not a
    similarity judgment."""
    chunk = Chunk(
        index=0,
        text="a hundred years old",
        char_start=0,
        char_end=20,
        locator="Genesis 21:5",
        ordinal=5,
        section="Genesis 21",
    )
    store.add_chunks([chunk], embeddings=[[1.0, 0.0]], metadata=_metadata(source_id="s1"))

    (hit,) = store.document_matches("hundred")

    assert hit.locator == "Genesis 21:5"
    assert hit.ordinal == 5
    assert hit.section == "Genesis 21"
    assert hit.source_id == "s1"
    assert hit.distance == 0.0


def test_document_frequency_counts_word_bounded_matches(store: ChromaVectorStore) -> None:
    chunks = [
        Chunk(index=0, text="he lived for 50 years", char_start=0, char_end=22),
        Chunk(index=1, text="the sum was 150 talents", char_start=23, char_end=47),
        Chunk(index=2, text="another 50 sheep", char_start=48, char_end=65),
    ]
    store.add_chunks(chunks, embeddings=[[1.0, 0.0]] * 3, metadata=_metadata(source_id="s1"))

    assert store.document_frequency("50") == 2
    assert store.document_frequency("150") == 1
    assert store.document_frequency("nonexistent") == 0
