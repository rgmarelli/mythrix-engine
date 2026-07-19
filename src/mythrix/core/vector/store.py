"""`ChromaVectorStore`: embedded Chroma persistence for ingested document chunks
(plan.md "Chroma vector store design").

Deliberately takes precomputed embeddings on every call rather than embedding
internally — the store never invokes an embedding model itself, so a unit test
can inject arbitrary fake vectors and a real caller (document loader, retrieval
pipeline) is free to swap embedding backends without touching this module. This
mirrors the `Embedder` abstraction plan.md's Risks section calls for.

Single `mythrix_sources` collection, not per-tradition, so a future
cross-tradition query doesn't need to fan out across collections — `tradition`
and `domain` are metadata filters instead.

The collection is configured for cosine distance explicitly (rather than
Chroma's l2 default), since cosine is the standard choice for text embeddings
and it gives `VectorHit.distance` a predictable `[0, 2]` range — `1 - distance`
is a stable similarity score in `RetrievalPipeline` (T15), which an l2 distance
(unbounded, scale-dependent on the embedding model) would not support.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from pydantic import BaseModel, ConfigDict

from mythrix.core.vector.chunking import Chunk

DEFAULT_COLLECTION_NAME = "mythrix_sources"


class ChunkMetadata(BaseModel):
    """Metadata shared by every chunk ingested from one document (plan.md's
    "Chunk metadata" list)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    tradition_slug: str
    domain: str
    embedding_model: str
    ingested_at: str


class VectorHit(BaseModel):
    """One raw similarity-search result — deliberately lighter than
    `core.models.RetrievedPassage`: it carries only what Chroma itself knows
    (ids, metadata, text, distance), not the hydrated `Source`/`Tradition`
    objects a `RetrievedPassage` needs. Joining this against `KuzuGraphStore` to
    build a full `RetrievedPassage` is `RetrievalPipeline`'s job (T15), not the
    vector store's."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str
    source_id: str
    tradition_slug: str
    domain: str
    text: str
    chunk_index: int
    char_start: int
    char_end: int
    embedding_model: str
    distance: float
    locator: str = ""


def _chunk_id(source_id: str, chunk_index: int) -> str:
    return f"{source_id}::{chunk_index}"


class ChromaVectorStore:
    """Owns a persistent Chroma client and the single `mythrix_sources` collection."""

    def __init__(self, persist_dir: Path, *, collection_name: str = DEFAULT_COLLECTION_NAME) -> None:
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(collection_name, metadata={"hnsw:space": "cosine"})

    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]], metadata: ChunkMetadata) -> None:
        """Adds every chunk from one document, all sharing `metadata`. Each
        chunk's own fields (`chunk_index`/`char_start`/`char_end`) are merged in
        per-chunk. Upserts by id (`source_id::chunk_index`), so re-adding the
        same source's chunks (e.g. after `delete_by_source`) doesn't duplicate.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(f"Got {len(chunks)} chunks but {len(embeddings)} embeddings.")
        if not chunks:
            return

        ids = [_chunk_id(metadata.source_id, chunk.index) for chunk in chunks]
        documents = [chunk.text for chunk in chunks]
        metadatas: list[dict[str, Any]] = [
            {
                **metadata.model_dump(),
                "chunk_index": chunk.index,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "locator": chunk.locator,
            }
            for chunk in chunks
        ]
        self._collection.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)

    def similarity_search(
        self,
        query_embedding: list[float],
        *,
        tradition_slug: str | None = None,
        top_k: int = 6,
        document_contains: str | None = None,
    ) -> list[VectorHit]:
        """Retrieves the `top_k` chunks nearest `query_embedding`, optionally
        scoped to one tradition (FR7) — never an unfiltered corpus-wide search
        when a tradition is known.

        `document_contains`, if given, restricts results to chunks whose raw
        text literally contains that substring (Chroma's `where_document`),
        combined with the embedding ranking rather than replacing it — for a
        fact that's an exact value rather than a fuzzy meaning (e.g. a Hebrew
        letter's gematria value), semantic similarity alone can't tell "this
        chunk happens to mention some number" from "this chunk mentions
        exactly this number"; the literal filter narrows to chunks that
        actually contain it, and embedding similarity still picks the most
        relevant among those. This *does* exclude every chunk that doesn't
        contain the substring, hard — a caller that wants the filter to be a
        boost rather than a requirement (e.g. `RetrievalPipeline`, see its
        module docstring) should call this twice, once with the filter and
        once without, and combine both result sets itself, rather than
        expecting this method to do that softening on its own.
        """
        where = {"tradition_slug": tradition_slug} if tradition_slug is not None else None
        where_document = {"$contains": document_contains} if document_contains is not None else None
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            where_document=where_document,
            include=["documents", "metadatas", "distances"],
        )
        if not result["ids"] or not result["ids"][0]:
            return []

        hits = []
        for chunk_id, document, meta, distance in zip(
            result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0], strict=True
        ):
            hits.append(
                VectorHit(
                    chunk_id=chunk_id,
                    source_id=meta["source_id"],
                    tradition_slug=meta["tradition_slug"],
                    domain=meta["domain"],
                    text=document,
                    chunk_index=meta["chunk_index"],
                    char_start=meta["char_start"],
                    char_end=meta["char_end"],
                    embedding_model=meta["embedding_model"],
                    distance=distance,
                    locator=meta.get("locator") or "",
                )
            )
        return hits

    def delete_by_source(self, source_id: str) -> None:
        """Removes every chunk previously ingested for `source_id` — the
        "replace" half of FR23's changed-file path."""
        self._collection.delete(where={"source_id": source_id})

    def count(self) -> int:
        return self._collection.count()
