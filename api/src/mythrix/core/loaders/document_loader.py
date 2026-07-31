# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

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
from mythrix.core.retrieval.locator_format import chapter_section_locator
from mythrix.core.vector.chunking import Chunk, chunk_text
from mythrix.core.vector.segmentation import segment_text
from mythrix.core.vector.store import ChromaVectorStore, ChunkMetadata

_EMBED_BATCH_SIZE = 64


def _structure_signature(source: Source) -> str:
    """Canonical string form of a source's declared `structure:` block
    (FR-CO-13) — folded into its content hash so editing only the structure
    declaration (e.g. tuning a `chapter_section` pattern) is detected as a
    change exactly like editing the raw text is, rather than going unnoticed
    because `_hash_content` only ever looked at the `.txt` bytes."""
    return "\x1f".join(
        (
            source.structure_scheme,
            source.chapter_pattern,
            source.subsection_pattern,
            str(source.body_start_occurrence),
            str(source.body_end_occurrence),
        )
    )


def _hash_content(content: str, structure_signature: str = "") -> str:
    return hashlib.sha256(f"{content}\x00{structure_signature}".encode()).hexdigest()


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
    content_hash = _hash_content(content, _structure_signature(source))

    if content_hash == source.content_hash:
        return 0

    if source.content_hash:
        vector_store.delete_by_source(source_id)

    if source.structure_scheme:
        chunks = segment_text(
            content,
            scheme=source.structure_scheme,
            chapter_pattern=source.chapter_pattern or None,
            subsection_pattern=source.subsection_pattern or None,
            body_start_occurrence=source.body_start_occurrence,
            body_end_occurrence=source.body_end_occurrence,
        )
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
    structure = parsed.source.structure
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
        structure_scheme=structure.scheme if structure else "",
        chapter_pattern=(structure.chapter_pattern or "") if structure else "",
        subsection_pattern=(structure.subsection_pattern or "") if structure else "",
        body_start_occurrence=structure.body_start_occurrence if structure else 1,
        body_end_occurrence=structure.body_end_occurrence if structure else 0,
    )


def _existing_source(graph_store: KuzuGraphStore, source_id: str) -> Source | None:
    try:
        return graph_store.get_source(source_id)
    except SourceNotFoundError:
        return None


def _segment_source(content: str, source: Source, *, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    """Runs the source's declared segmentation (or the fixed-size fallback)
    against its actual text. Shared by `_segmentation_summary` (chapter/count
    shape) and `preview_corpus_segments` (every segment's own locator) so the
    two previews can never compute segments differently from each other, or
    from a real ingest's own `load_document` call."""
    if source.structure_scheme:
        return segment_text(
            content,
            scheme=source.structure_scheme,
            chapter_pattern=source.chapter_pattern or None,
            subsection_pattern=source.subsection_pattern or None,
            body_start_occurrence=source.body_start_occurrence,
            body_end_occurrence=source.body_end_occurrence,
        )
    return chunk_text(content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def _segmentation_summary(content: str, source: Source, *, chunk_size: int, chunk_overlap: int) -> dict:
    """Runs the source's declared segmentation (or the fixed-size fallback)
    against its actual text purely to report shape (FR-CO-14) — no
    embedding, no graph/vector-store write. For `chapter_section`, includes
    each detected chapter label and how many segments fall under it, so a
    curator can validate a candidate pattern (e.g. checking the detected
    chapter count against the source's own table of contents) before a real,
    costly ingest runs."""
    chunks = _segment_source(content, source, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    summary: dict = {"total_segments": len(chunks)}
    if source.structure_scheme == "chapter_section":
        counts: dict[str, int] = {}
        order: list[str] = []
        for chunk in chunks:
            label = chunk.section or chunk.locator
            if label not in counts:
                order.append(label)
                counts[label] = 0
            counts[label] += 1
        summary["chapters"] = [{"label": label, "segments": counts[label]} for label in order]
    return summary


def _discover_corpus_pairs(root: Path) -> list[tuple[Path, Source]]:
    """Every `<name>.yaml` under `root` paired with its sibling `<name>.txt`,
    each parsed into a `Source` (FR-CO-01) — no `--tradition`/`--domain`/
    `--source-slug` flags needed, since a corpus source's own YAML already
    carries its `id`/`domain` directly. All pairs are parsed before any
    caller acts on one, so a duplicate `id` across corpus files is caught
    before any of them is registered, ingested, or previewed — mirrors
    `sign_loader.py`'s two-phase discipline. Shared by `load_corpus_directory`
    and `preview_corpus_segments` so both discover sources identically."""
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
    return pairs


def preview_corpus_segments(root: Path, *, chunk_size: int = 650, chunk_overlap: int = 100) -> list[dict]:
    """For every corpus source discovered under `root`, runs its declared
    segmentation against its actual text and returns every resulting
    segment's own ordinal/locator/section (FR-CO-14) — the fine-grained
    sibling of `load_corpus_directory(dry_run=True)`'s per-chapter counts,
    for when a curator needs to see the actual locator text a pattern change
    produces (e.g. does a subsection-level segment still name its chapter?)
    rather than just how many segments land in each chapter.

    Touches neither the graph store nor the vector store — no `Source`
    lookup, no content-hash comparison, nothing opened at all — so unlike
    `load_corpus_directory`, this never needs a `KuzuGraphStore`/
    `ChromaVectorStore` handle and never contends with one already open
    elsewhere (e.g. a running API server holding Kùzu's single-writer lock).

    A `chapter_section` chunk's own `locator` is always empty at this point
    (formatting happens at query time, not ingest — see
    `mythrix.core.retrieval.locator_format`), so its display locator is
    built here via `chapter_section_locator` instead, the same call every
    real query-path `Segment` construction makes — this previews exactly
    what the app will render, not raw structural fields.
    """
    results: list[dict] = []
    for txt_path, source in _discover_corpus_pairs(root):
        content = txt_path.read_text(encoding="utf-8")
        chunks = _segment_source(content, source, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        results.append(
            {
                "source_id": source.id,
                "segments": [
                    {
                        "ordinal": chunk.ordinal,
                        "locator": chapter_section_locator(chunk, chunk) if chunk.chapter_title else chunk.locator,
                        "section": chunk.section,
                    }
                    for chunk in chunks
                ],
            }
        )
    return results


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
    """Auto-discovers every corpus source under `root` (`_discover_corpus_pairs`)
    and either previews or ingests each one.

    `dry_run=True` hashes each `.txt` plus its declared `structure` block
    (FR-CO-13) and compares that against the corresponding `Source`'s
    recorded `content_hash` if one is already declared; it also runs the
    source's declared segmentation against its actual text to report a
    structural summary (FR-CO-14) — neither writes anything, and
    `vector_store`/`embedder` may be `None`.

    Returns one result dict per discovered source: `{"source_id", "status",
    "detail", "segmentation"}` for a dry run, `{"source_id",
    "chunks_written"}` for a real one.
    """
    pairs = _discover_corpus_pairs(root)

    results: list[dict] = []
    for txt_path, source in pairs:
        existing = _existing_source(graph_store, source.id)

        if dry_run:
            content = txt_path.read_text(encoding="utf-8")
            content_hash = _hash_content(content, _structure_signature(source))
            existing_hash = existing.content_hash if existing else ""
            if content_hash == existing_hash:
                status, detail = "unchanged", "no-op — file matches what's already ingested"
            elif existing_hash:
                status, detail = "changed", "would replace this source's existing chunks"
            else:
                status, detail = "new", "would ingest for the first time"
            segmentation = _segmentation_summary(content, source, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            results.append({"source_id": source.id, "status": status, "detail": detail, "segmentation": segmentation})
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
