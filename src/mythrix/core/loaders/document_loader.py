"""Ingests one primary-source document into the vector store, keyed to a
`Source` already declared in the Symbol Graph (`symbol_loader.py`).

Idempotent/updatable via a content hash recorded on the `Source` node (FR23):
unseen hash -> chunk/embed/add; unchanged hash -> no-op; changed hash -> delete
the source's old chunks before adding the new ones. See plan.md's "Idempotent/
updatable ingestion via content hash" section.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from mythrix.core.embedding import Embedder
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.vector.chunking import chunk_text
from mythrix.core.vector.store import ChromaVectorStore, ChunkMetadata

_EMBED_BATCH_SIZE = 64


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _embed_in_batches(embedder: Embedder, texts: list[str]) -> list[list[float]]:
    """A single request for a whole large document (thousands of chunks) risks an
    oversized payload the local Ollama daemon can't handle in one shot — batch it
    instead, so a large document degrades to "slower" rather than "fails outright"."""
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), _EMBED_BATCH_SIZE):
        embeddings.extend(embedder.embed(texts[start : start + _EMBED_BATCH_SIZE]))
    return embeddings


def load_document(
    path: Path,
    *,
    source_id: str,
    tradition_slug: str,
    domain: str,
    graph_store: KuzuGraphStore,
    vector_store: ChromaVectorStore,
    embedder: Embedder,
    chunk_size: int = 650,
    chunk_overlap: int = 100,
) -> int:
    """Ingests the file at `path` for `source_id`. Returns the number of chunks
    written (0 for a no-op when the file is unchanged since the last ingest).

    Raises `SourceNotFoundError` if `source_id` hasn't been declared via the
    structured-data loader yet (FR6) — a document is never ingested for a
    source nobody registered.
    """
    source = graph_store.get_source(source_id)
    content = path.read_text(encoding="utf-8")
    content_hash = _hash_content(content)

    if content_hash == source.content_hash:
        return 0

    if source.content_hash:
        vector_store.delete_by_source(source_id)

    chunks = chunk_text(content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if chunks:
        embeddings = _embed_in_batches(embedder, [chunk.text for chunk in chunks])
        metadata = ChunkMetadata(
            source_id=source_id,
            tradition_slug=tradition_slug,
            domain=domain,
            embedding_model=embedder.model_name,
            ingested_at=datetime.now(UTC).isoformat(),
        )
        vector_store.add_chunks(chunks, embeddings=embeddings, metadata=metadata)

    updated_source = source.model_copy(update={"content_hash": content_hash, "ingested_at": datetime.now(UTC)})
    graph_store.upsert_source(updated_source)

    return len(chunks)
