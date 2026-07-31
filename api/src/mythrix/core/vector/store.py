# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""`ChromaVectorStore`: embedded Chroma persistence for ingested document chunks.

Deliberately takes precomputed embeddings on every call rather than embedding
internally — the store never invokes an embedding model itself, so a unit test
can inject arbitrary fake vectors and a real caller (document loader, retrieval
pipeline) is free to swap embedding backends without touching this module.

Single `mythrix_sources` collection, not per-domain, so a future
cross-domain query doesn't need to fan out across collections — `domain` is
a metadata filter instead. Chunks carry no tradition: every ingested document
is an independent corpus document (FR-CO-02), which has no interpretive tradition
of its own.

The collection is configured for cosine distance explicitly (rather than
Chroma's l2 default), since cosine is the standard choice for text embeddings
and it gives `VectorHit.distance` a predictable `[0, 2]` range — `1 - distance`
is a stable similarity score in `RetrievalPipeline`, which an l2 distance
(unbounded, scale-dependent on the embedding model) would not support.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import chromadb
from pydantic import BaseModel, ConfigDict

from mythrix.core.vector.chunking import Chunk

DEFAULT_COLLECTION_NAME = "mythrix_sources"


class ChunkMetadata(BaseModel):
    """Metadata shared by every chunk ingested from one document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    domain: str
    embedding_model: str
    ingested_at: str


class VectorHit(BaseModel):
    """One raw similarity-search result: only what Chroma itself knows (ids,
    metadata, text, distance), never a hydrated `Source`. Joining this against
    `KuzuGraphStore` to attribute a segment is `RetrievalPipeline`'s job, not
    the vector store's."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str
    source_id: str
    domain: str
    text: str
    chunk_index: int
    char_start: int
    char_end: int
    embedding_model: str
    distance: float
    locator: str = ""
    ordinal: int = 0
    section: str = ""
    chapter_ordinal: int = 0
    chapter_title: str = ""
    subsection_ordinal: int = 0
    subsection_title: str = ""


def _chunk_id(source_id: str, chunk_index: int) -> str:
    return f"{source_id}::{chunk_index}"


def _word_bounded_filter(term: str) -> dict[str, str]:
    """A Chroma `where_document` constraint matching `term` on whole-word
    boundaries — `$regex`, not `$contains` substring matching (ADR-002,
    FR-RT-15): `\\b` prevents `50` from matching inside `150`."""
    return {"$regex": r"\b" + re.escape(term) + r"\b"}


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

        Upserts in batches of at most the client's own `get_max_batch_size()`
        (Chroma rejects a single call larger than that outright) — this only
        bites once fine-grained structural segmentation (FR-CO-05) turns one large
        document into tens of thousands of segments, far more than the
        word-count chunker ever produced in one call.
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
                "ordinal": chunk.ordinal,
                "section": chunk.section,
                "chapter_ordinal": chunk.chapter_ordinal,
                "chapter_title": chunk.chapter_title,
                "subsection_ordinal": chunk.subsection_ordinal,
                "subsection_title": chunk.subsection_title,
            }
            for chunk in chunks
        ]
        batch_size = self._client.get_max_batch_size()
        for start in range(0, len(chunks), batch_size):
            end = start + batch_size
            self._collection.upsert(
                ids=ids[start:end],
                documents=documents[start:end],
                embeddings=embeddings[start:end],
                metadatas=metadatas[start:end],
            )

    def similarity_search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 6,
        document_contains: str | None = None,
    ) -> list[VectorHit]:
        """Retrieves the `top_k` chunks nearest `query_embedding` from the full
        corpus (FR-CO-02) — there is no tradition to scope by; every ingested
        document is independent.

        `document_contains`, if given, restricts results to chunks whose raw
        text contains that token on whole-word boundaries (Chroma's
        `where_document` `$regex`, not `$contains` substring matching — a
        token must not match inside a larger word or number, e.g. `50` must
        not match inside `150`; see FR-RT-15),
        combined with the embedding ranking rather than replacing it — for a
        fact that's an exact value rather than a fuzzy meaning (e.g. a Hebrew
        letter's gematria value), semantic similarity alone can't tell "this
        chunk happens to mention some number" from "this chunk mentions
        exactly this number"; the literal filter narrows to chunks that
        actually contain it, and embedding similarity still picks the most
        relevant among those. This *does* exclude every chunk that doesn't
        contain the token, hard — a caller that wants the filter to be a
        boost rather than a requirement (e.g. `RetrievalPipeline`, see its
        module docstring) should call this twice, once with the filter and
        once without, and combine both result sets itself, rather than
        expecting this method to do that softening on its own.
        """
        where_document = _word_bounded_filter(document_contains) if document_contains is not None else None
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
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
                    domain=meta["domain"],
                    text=document,
                    chunk_index=meta["chunk_index"],
                    char_start=meta["char_start"],
                    char_end=meta["char_end"],
                    embedding_model=meta["embedding_model"],
                    distance=distance,
                    locator=meta.get("locator") or "",
                    ordinal=meta.get("ordinal") or 0,
                    section=meta.get("section") or "",
                    chapter_ordinal=meta.get("chapter_ordinal") or 0,
                    chapter_title=meta.get("chapter_title") or "",
                    subsection_ordinal=meta.get("subsection_ordinal") or 0,
                    subsection_title=meta.get("subsection_title") or "",
                )
            )
        return hits

    def document_matches(self, term: str) -> list[VectorHit]:
        """Every chunk whose text contains `term` on whole-word boundaries
        (FR-RT-15) — a pure document scan (`collection.get`), no query
        embedding and no `top_k` cap, unlike `similarity_search`. Used for a
        literal-containment directive (`"exact"`/`"filter"`) where the point
        is a guarantee every occurrence is found, not an approximate nearest-
        neighbor ranking: an ANN search combined with a document filter can
        still miss a chunk that ranks outside `top_k` among the filtered
        candidates, which this can't. `VectorHit.distance` is set to `0.0`
        for every result — there is no query vector here to measure a
        distance against, so this is a placeholder, not a similarity
        judgment; callers must not treat it as a score."""
        result = self._collection.get(where_document=_word_bounded_filter(term), include=["documents", "metadatas"])
        return [
            VectorHit(
                chunk_id=chunk_id,
                source_id=meta["source_id"],
                domain=meta["domain"],
                text=document,
                chunk_index=meta["chunk_index"],
                char_start=meta["char_start"],
                char_end=meta["char_end"],
                embedding_model=meta["embedding_model"],
                distance=0.0,
                locator=meta.get("locator") or "",
                ordinal=meta.get("ordinal") or 0,
                section=meta.get("section") or "",
                chapter_ordinal=meta.get("chapter_ordinal") or 0,
                chapter_title=meta.get("chapter_title") or "",
                subsection_ordinal=meta.get("subsection_ordinal") or 0,
                subsection_title=meta.get("subsection_title") or "",
            )
            for chunk_id, document, meta in zip(result["ids"], result["documents"], result["metadatas"], strict=True)
        ]

    def get_segments(self, source_id: str, *, start_ordinal: int, end_ordinal: int) -> list[Chunk]:
        """Every chunk of `source_id` with `ordinal` in `[start_ordinal,
        end_ordinal]`, sorted ascending by ordinal — a coordinate lookup for
        the web viewer's Add Context action (`hotspot-context-expansion`),
        not a similarity search: no query embedding, no ranking, no distance.

        `start_ordinal > end_ordinal` returns `[]` without querying, so a
        caller can pass an already-empty range (e.g. probing one step past a
        source's last segment) without a special case.
        """
        if start_ordinal > end_ordinal:
            return []

        result = self._collection.get(
            where={
                "$and": [
                    {"source_id": {"$eq": source_id}},
                    {"ordinal": {"$gte": start_ordinal}},
                    {"ordinal": {"$lte": end_ordinal}},
                ]
            },
            include=["documents", "metadatas"],
        )
        chunks = [
            Chunk(
                index=meta["chunk_index"],
                text=document,
                char_start=meta["char_start"],
                char_end=meta["char_end"],
                locator=meta.get("locator") or "",
                ordinal=meta.get("ordinal") or 0,
                section=meta.get("section") or "",
                chapter_ordinal=meta.get("chapter_ordinal") or 0,
                chapter_title=meta.get("chapter_title") or "",
                subsection_ordinal=meta.get("subsection_ordinal") or 0,
                subsection_title=meta.get("subsection_title") or "",
            )
            for document, meta in zip(result["documents"], result["metadatas"], strict=True)
        ]
        chunks.sort(key=lambda chunk: chunk.ordinal)
        return chunks

    def delete_by_source(self, source_id: str) -> None:
        """Removes every chunk previously ingested for `source_id` — the
        "replace" half of FR-CO-04's changed-file path."""
        self._collection.delete(where={"source_id": source_id})

    def count(self) -> int:
        return self._collection.count()

    def document_frequency(self, term: str) -> int:
        """Count of chunks whose text contains `term` on whole-word
        boundaries — the literal, lexical document frequency
        FR-RK-04/FR-RK-06 specificity weighting is
        built from (never a count derived from dense embedding scores). A
        per-query `$regex` scan, kept behind this narrow method so an
        ingest-time df table (ADR-003, ADR-005) can replace it later
        without changing any caller."""
        result = self._collection.get(where_document=_word_bounded_filter(term), include=[])
        return len(result["ids"])
