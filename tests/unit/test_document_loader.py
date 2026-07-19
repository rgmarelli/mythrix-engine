"""Unit tests for the document loader (T14): source validation and
content-hash-based idempotent/updatable ingestion (FR23). Uses a fake
`Embedder` — no Ollama needed."""

from pathlib import Path

import pytest

from mythrix.core.errors import SourceNotFoundError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.loaders.document_loader import load_document
from mythrix.core.models import Source
from mythrix.core.vector.store import ChromaVectorStore


class FakeEmbedder:
    model_name = "fake-embed"

    def __init__(self) -> None:
        self.call_sizes: list[int] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_sizes.append(len(texts))
        return [[float(len(text)), 0.0] for text in texts]


@pytest.fixture
def graph_store(tmp_path: Path) -> KuzuGraphStore:
    return KuzuGraphStore(tmp_path / "graph.kuzu")


@pytest.fixture
def vector_store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(tmp_path / "chroma")


def _declare_source(graph_store: KuzuGraphStore, source_id: str = "waite-pictorial-key") -> None:
    graph_store.upsert_source(Source(id=source_id, title="The Pictorial Key to the Tarot", author="A. E. Waite"))


def test_loading_for_an_undeclared_source_raises_and_writes_nothing(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    doc = tmp_path / "excerpt.txt"
    doc.write_text("Some primary source text.", encoding="utf-8")

    with pytest.raises(SourceNotFoundError):
        load_document(
            doc,
            source_id="nonexistent",
            tradition_slug="rider-waite",
            domain="tarot",
            graph_store=graph_store,
            vector_store=vector_store,
            embedder=FakeEmbedder(),
        )
    assert vector_store.count() == 0


def test_first_ingest_writes_chunks_and_records_hash(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    _declare_source(graph_store)
    doc = tmp_path / "excerpt.txt"
    doc.write_text("The Tower depicts sudden upheaval, the collapse of false structures.", encoding="utf-8")

    written = load_document(
        doc,
        source_id="waite-pictorial-key",
        tradition_slug="rider-waite",
        domain="tarot",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
    )

    assert written == 1
    assert vector_store.count() == 1
    source = graph_store.get_source("waite-pictorial-key")
    assert source.content_hash != ""
    assert source.ingested_at is not None


def test_reingesting_unchanged_file_is_a_noop(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    _declare_source(graph_store)
    doc = tmp_path / "excerpt.txt"
    doc.write_text("The Tower depicts sudden upheaval.", encoding="utf-8")
    load_document(
        doc,
        source_id="waite-pictorial-key",
        tradition_slug="rider-waite",
        domain="tarot",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
    )
    hash_after_first_load = graph_store.get_source("waite-pictorial-key").content_hash

    written = load_document(
        doc,
        source_id="waite-pictorial-key",
        tradition_slug="rider-waite",
        domain="tarot",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
    )

    assert written == 0
    assert vector_store.count() == 1
    assert graph_store.get_source("waite-pictorial-key").content_hash == hash_after_first_load


def test_reingesting_changed_file_replaces_chunks(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    _declare_source(graph_store)
    doc = tmp_path / "excerpt.txt"
    doc.write_text("The original paragraph about The Tower.", encoding="utf-8")
    load_document(
        doc,
        source_id="waite-pictorial-key",
        tradition_slug="rider-waite",
        domain="tarot",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
    )
    original_hash = graph_store.get_source("waite-pictorial-key").content_hash

    doc.write_text("A revised, corrected paragraph about The Tower and its meaning.", encoding="utf-8")
    written = load_document(
        doc,
        source_id="waite-pictorial-key",
        tradition_slug="rider-waite",
        domain="tarot",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
    )

    assert written == 1
    assert vector_store.count() == 1  # replaced, not accumulated
    hits = vector_store.similarity_search(
        [float(len("A revised, corrected paragraph about The Tower and its meaning.")), 0.0], top_k=1
    )
    assert "revised" in hits[0].text
    new_hash = graph_store.get_source("waite-pictorial-key").content_hash
    assert new_hash != original_hash


def test_large_document_is_embedded_in_batches_not_one_giant_request(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    """A single request for a whole large document risks an oversized payload the
    local Ollama daemon can't handle (the real failure this project hit trying to
    ingest the full Bible) — chunks must go out in bounded batches."""
    _declare_source(graph_store)
    doc = tmp_path / "large.txt"
    doc.write_text(" ".join(f"word{i}" for i in range(2000)), encoding="utf-8")
    embedder = FakeEmbedder()

    written = load_document(
        doc,
        source_id="waite-pictorial-key",
        tradition_slug="rider-waite",
        domain="tarot",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=embedder,
        chunk_size=20,
        chunk_overlap=0,
    )

    assert written > 64
    assert len(embedder.call_sizes) > 1
    assert all(size <= 64 for size in embedder.call_sizes)
    assert sum(embedder.call_sizes) == written
    assert vector_store.count() == written
