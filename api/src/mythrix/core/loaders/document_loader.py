"""Ingests primary-source documents into the vector store, each keyed to a
`Source` declared in the Sign Graph (FR-CO-01).

Idempotent/updatable via a content hash recorded on the `Source` node (FR-CO-04):
unseen hash -> chunk/embed/add; unchanged hash -> no-op; changed hash -> delete
the source's old chunks before adding the new ones.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import yaml

from mythrix.core.embedding import Embedder
from mythrix.core.errors import IngestValidationError, SourceNotFoundError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.loaders.sign_schema import SourceFile
from mythrix.core.models import Source
from mythrix.core.vector.chunking import chunk_text
from mythrix.core.vector.segmentation import segment_text
from mythrix.core.vector.store import ChromaVectorStore, ChunkMetadata

_EMBED_BATCH_SIZE = 64


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _read_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


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
    graph_store: KuzuGraphStore,
    vector_store: ChromaVectorStore,
    embedder: Embedder,
    chunk_size: int = 650,
    chunk_overlap: int = 100,
) -> int:
    """Ingests the file at `path` for `source_id`. Returns the number of chunks
    written (0 for a no-op when the file is unchanged since the last ingest).

    `domain` for the ingested chunks comes from the already-declared
    `Source.domain`, not a caller-supplied argument — a chunk's domain is a
    fact about its source, not a fact about the call site.

    When the source declares a `structure_scheme` (FR-CO-05), ingestion routes through that structural segmenter instead of the
    fixed word-count `chunk_text`; `chunk_size`/`chunk_overlap` are then unused.

    Raises `SourceNotFoundError` if `source_id` hasn't been declared yet
    (FR-CO-01) — a document is never ingested for a source nobody registered.
    """
    source = graph_store.get_source(source_id)
    content = path.read_text(encoding="utf-8")
    content_hash = _hash_content(content)

    if content_hash == source.content_hash:
        return 0

    if source.content_hash:
        vector_store.delete_by_source(source_id)

    if source.structure_scheme:
        chunks = segment_text(content, scheme=source.structure_scheme)
    else:
        chunks = chunk_text(content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if chunks:
        embeddings = _embed_in_batches(embedder, [chunk.text for chunk in chunks])
        metadata = ChunkMetadata(
            source_id=source_id,
            domain=source.domain,
            embedding_model=embedder.model_name,
            ingested_at=datetime.now(UTC).isoformat(),
        )
        vector_store.add_chunks(chunks, embeddings=embeddings, metadata=metadata)

    updated_source = source.model_copy(update={"content_hash": content_hash, "ingested_at": datetime.now(UTC)})
    graph_store.upsert_source(updated_source)

    return len(chunks)


def _parse_corpus_source(yaml_path: Path) -> Source:
    try:
        parsed = SourceFile.model_validate(_read_yaml(yaml_path))
    except Exception as exc:  # noqa: BLE001 - re-raised with file context below
        raise IngestValidationError(str(exc), source_path=str(yaml_path)) from exc
    return Source(
        id=parsed.source.id,
        domain=parsed.source.domain,
        citation_label=parsed.source.citation_label,
        title=parsed.source.title,
        author=parsed.source.author,
        publication_year=parsed.source.publication_year,
        license=parsed.source.license,
        uri=parsed.source.uri,
        description=parsed.source.description,
        structure_scheme=parsed.source.structure.scheme if parsed.source.structure else "",
    )


def _existing_source(graph_store: KuzuGraphStore, source_id: str) -> Source | None:
    try:
        return graph_store.get_source(source_id)
    except SourceNotFoundError:
        return None


def load_corpus_directory(
    root: Path,
    *,
    graph_store: KuzuGraphStore,
    vector_store: ChromaVectorStore | None,
    embedder: Embedder | None,
    chunk_size: int = 650,
    chunk_overlap: int = 100,
    dry_run: bool = False,
) -> list[dict]:
    """Auto-discovers every corpus source under `root`: each `<name>.yaml`
    colocated with a `<name>.txt` of the same stem is one source (FR-CO-01) —
    no `--tradition`/`--domain`/`--source-slug` flags needed, since a corpus
    source's own YAML already carries its `id`/`domain` directly. Unlike a
    sign's own citation sources, a corpus document is never assigned a
    tradition — FR-CO-02's independent-corpus reading has no interpretive lens of
    its own.

    Every pair is parsed before anything is written, so a duplicate `id`
    across corpus files is caught before any of them is registered or
    ingested — mirrors `sign_loader.py`'s two-phase discipline.

    `dry_run=True` only hashes each `.txt` and compares it against the
    corresponding `Source`'s recorded `content_hash` if one is already
    declared; nothing is written, and `vector_store`/`embedder` may be `None`.

    Returns one result dict per discovered source: `{"source_id", "status",
    "detail"}` for a dry run, `{"source_id", "chunks_written"}` for a real one.
    """
    pairs: list[tuple[Path, Source]] = []
    seen_ids: set[str] = set()
    for yaml_path in sorted(root.rglob("*.yaml")):
        txt_path = yaml_path.with_suffix(".txt")
        if not txt_path.exists():
            continue
        source = _parse_corpus_source(yaml_path)
        if source.id in seen_ids:
            raise IngestValidationError(f"Duplicate corpus source id {source.id!r}.", source_path=str(yaml_path))
        seen_ids.add(source.id)
        pairs.append((txt_path, source))

    results: list[dict] = []
    for txt_path, source in pairs:
        existing = _existing_source(graph_store, source.id)

        if dry_run:
            content_hash = _hash_content(txt_path.read_text(encoding="utf-8"))
            existing_hash = existing.content_hash if existing else ""
            if content_hash == existing_hash:
                status, detail = "unchanged", "no-op — file matches what's already ingested"
            elif existing_hash:
                status, detail = "changed", "would replace this source's existing chunks"
            else:
                status, detail = "new", "would ingest for the first time"
            results.append({"source_id": source.id, "status": status, "detail": detail})
            continue

        # Refresh the source's own metadata on every pass without disturbing
        # `content_hash`/`ingested_at` — those are `load_document`'s to set,
        # based on the file it actually reads, not this registration step.
        registered = source.model_copy(
            update={
                "content_hash": existing.content_hash if existing else "",
                "ingested_at": existing.ingested_at if existing else None,
            }
        )
        graph_store.upsert_source(registered)
        chunks_written = load_document(
            txt_path,
            source_id=source.id,
            graph_store=graph_store,
            vector_store=vector_store,
            embedder=embedder,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        results.append({"source_id": source.id, "chunks_written": chunks_written})

    return results
