"""Unit tests for the document loader (T14): source validation and
content-hash-based idempotent/updatable ingestion (FR-CO-04), plus corpus
directory auto-discovery. Uses a fake `Embedder` — no Ollama needed."""

from pathlib import Path

import pytest

from mythrix.core.errors import IngestValidationError, SourceNotFoundError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.loaders.document_loader import load_corpus_directory, load_document
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
    graph_store.upsert_source(
        Source(id=source_id, domain="tarot", title="The Pictorial Key to the Tarot", author="A. E. Waite")
    )


def test_loading_for_an_undeclared_source_raises_and_writes_nothing(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    doc = tmp_path / "excerpt.txt"
    doc.write_text("Some primary source text.", encoding="utf-8")

    with pytest.raises(SourceNotFoundError):
        load_document(
            doc,
            source_id="nonexistent",
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
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
    )

    assert written == 1
    assert vector_store.count() == 1
    source = graph_store.get_source("waite-pictorial-key")
    assert source.content_hash != ""
    assert source.ingested_at is not None


def test_ingested_chunk_carries_the_sources_own_domain(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    """A chunk's `domain` comes from the already-declared `Source.domain` —
    not a caller-supplied argument (there is no tradition/domain kwarg left
    on `load_document` to pass one through)."""
    _declare_source(graph_store)
    doc = tmp_path / "excerpt.txt"
    doc.write_text("The Tower depicts sudden upheaval.", encoding="utf-8")

    load_document(
        doc,
        source_id="waite-pictorial-key",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
    )

    hits = vector_store.similarity_search([len("The Tower depicts sudden upheaval."), 0.0], top_k=1)
    assert hits[0].domain == "tarot"


def test_reingesting_unchanged_file_is_a_noop(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    _declare_source(graph_store)
    doc = tmp_path / "excerpt.txt"
    doc.write_text("The Tower depicts sudden upheaval.", encoding="utf-8")
    load_document(
        doc,
        source_id="waite-pictorial-key",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
    )
    hash_after_first_load = graph_store.get_source("waite-pictorial-key").content_hash

    written = load_document(
        doc,
        source_id="waite-pictorial-key",
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
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
    )
    original_hash = graph_store.get_source("waite-pictorial-key").content_hash

    doc.write_text("A revised, corrected paragraph about The Tower and its meaning.", encoding="utf-8")
    written = load_document(
        doc,
        source_id="waite-pictorial-key",
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


def test_source_with_a_declared_structure_scheme_routes_through_the_segmenter(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    graph_store.upsert_source(
        Source(
            id="en_bahir", domain="kabbalah", title="Sefer HaBahir", author="Anon.", structure_scheme="numbered_section"
        )
    )
    doc = tmp_path / "excerpt.txt"
    doc.write_text("1. First section.\n\n2. Second section.\n", encoding="utf-8")

    written = load_document(
        doc,
        source_id="en_bahir",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
    )

    assert written == 2
    hits = vector_store.similarity_search([len("First section."), 0.0], top_k=5)
    assert {hit.locator for hit in hits} == {"§1", "§2"}
    assert {hit.section for hit in hits} == {""}
    assert all("1." not in hit.text and "2." not in hit.text for hit in hits)


def test_source_without_a_structure_scheme_falls_back_to_word_count_chunking(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    _declare_source(graph_store)
    doc = tmp_path / "excerpt.txt"
    doc.write_text("The Tower depicts sudden upheaval.", encoding="utf-8")

    load_document(
        doc,
        source_id="waite-pictorial-key",
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=FakeEmbedder(),
    )

    hits = vector_store.similarity_search([len("The Tower depicts sudden upheaval."), 0.0], top_k=1)
    assert hits[0].section == ""


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


# --- load_corpus_directory: auto-discovery ---


def _write_corpus_source(
    directory: Path, *, id_: str, filename_stem: str, domain: str = "scripture", text: str = "Some corpus text."
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{filename_stem}.yaml").write_text(
        f'source:\n  id: "{id_}"\n  domain: {domain}\n  citation_label: "Label"\n'
        f'  title: "Title"\n  author: "Author"\n',
        encoding="utf-8",
    )
    (directory / f"{filename_stem}.txt").write_text(text, encoding="utf-8")


def test_load_corpus_directory_registers_source_and_ingests_colocated_text(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    """A corpus source's `id`/`domain`/`citation_label` come entirely from its
    own colocated YAML — no `--tradition`/`--source-slug` flags needed."""
    corpus = tmp_path / "scripture" / "en_drb"
    _write_corpus_source(corpus, id_="en_drb", filename_stem="douay-rheims-bible", text="In the beginning.")

    results = load_corpus_directory(
        tmp_path, graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder()
    )

    assert results == [{"source_id": "en_drb", "chunks_written": 1}]
    source = graph_store.get_source("en_drb")
    assert source.domain == "scripture"
    assert source.citation_label == "Label"
    assert source.content_hash != ""
    assert vector_store.count() == 1


def test_load_corpus_directory_dry_run_writes_nothing(tmp_path: Path, graph_store: KuzuGraphStore) -> None:
    corpus = tmp_path / "scripture" / "en_drb"
    _write_corpus_source(corpus, id_="en_drb", filename_stem="douay-rheims-bible")

    results = load_corpus_directory(tmp_path, graph_store=graph_store, vector_store=None, embedder=None, dry_run=True)

    assert results == [{"source_id": "en_drb", "status": "new", "detail": "would ingest for the first time"}]
    with pytest.raises(SourceNotFoundError):
        graph_store.get_source("en_drb")


def test_load_corpus_directory_ignores_a_yaml_with_no_colocated_txt(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    orphan = tmp_path / "orphan"
    orphan.mkdir()
    (orphan / "no-text.yaml").write_text(
        'source:\n  id: "orphan"\n  domain: scripture\n  title: "T"\n  author: "A"\n', encoding="utf-8"
    )

    results = load_corpus_directory(
        tmp_path, graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder()
    )

    assert results == []


def test_load_corpus_directory_rejects_duplicate_source_ids_before_writing_anything(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    _write_corpus_source(tmp_path / "a", id_="dup", filename_stem="doc")
    _write_corpus_source(tmp_path / "b", id_="dup", filename_stem="doc")

    with pytest.raises(IngestValidationError, match="Duplicate corpus source id"):
        load_corpus_directory(tmp_path, graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())

    assert vector_store.count() == 0
    with pytest.raises(SourceNotFoundError):
        graph_store.get_source("dup")


def test_load_corpus_directory_reingesting_unchanged_is_a_noop(
    tmp_path: Path, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    corpus = tmp_path / "scripture" / "en_drb"
    _write_corpus_source(corpus, id_="en_drb", filename_stem="douay-rheims-bible")

    load_corpus_directory(tmp_path, graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())
    results = load_corpus_directory(
        tmp_path, graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder()
    )

    assert results == [{"source_id": "en_drb", "chunks_written": 0}]
    assert vector_store.count() == 1
