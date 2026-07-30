# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""`mythrix load-documents`: wraps `document_loader.load_corpus_directory`
(FR-CO-01, FR-CO-04).

Auto-discovers every corpus source under `path` — each `<name>.yaml`
colocated with a `<name>.txt` of the same stem — registering the `Source`
from its own YAML (`id`/`domain`/`citation_label`) and ingesting its text.
No `--tradition`/`--domain`/`--source-slug` flags: a corpus document is never
assigned a tradition (FR-CO-02), and its id/domain are authored directly in its
own file, not repeated on the command line.

`--dry-run` hashes each `.txt` plus its declared `structure` block
(FR-CO-13) and compares that to its `Source`'s recorded `content_hash`, and
runs the declared segmentation against the actual text to preview its
structural shape — chapter/segment counts (FR-CO-14) — without embedding
anything. It never constructs an embedder or vector store, so it works even
without a reachable Ollama daemon, and it's the way to validate a
`chapter_section` source's patterns before a real ingest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from mythrix.core.config import Settings
from mythrix.core.embedding import OllamaEmbedder
from mythrix.core.errors import MythrixError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.loaders.document_loader import load_corpus_directory
from mythrix.core.vector.store import ChromaVectorStore


def _format_segmentation(segmentation: dict) -> str:
    """Short, scannable summary of a dry-run segmentation preview
    (FR-CO-14) — full per-chapter detail is available via `--json`."""
    total = segmentation["total_segments"]
    unit = "segment" if total == 1 else "segments"
    chapters = segmentation.get("chapters")
    if chapters is not None:
        chapter_unit = "chapter" if len(chapters) == 1 else "chapters"
        return f"{total} {unit} across {len(chapters)} {chapter_unit}"
    return f"{total} {unit}"


def run_load_documents(
    path: Path,
    *,
    graph_store: KuzuGraphStore,
    vector_store: ChromaVectorStore | None,
    embedder: object | None,
    chunk_size: int,
    chunk_overlap: int,
    dry_run: bool,
    as_json: bool,
) -> int:
    try:
        results = load_corpus_directory(
            path,
            graph_store=graph_store,
            vector_store=vector_store,
            embedder=embedder,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            dry_run=dry_run,
        )
    except MythrixError as exc:
        typer.echo(f"Error: {exc}", err=True)
        return 1

    if as_json:
        typer.echo(json.dumps({"dry_run": dry_run, "results": results}, indent=2))
    elif not results:
        typer.echo("No corpus sources found.")
    elif dry_run:
        for result in results:
            summary = _format_segmentation(result["segmentation"])
            typer.echo(f"{result['source_id']!r}: {result['status']} — {result['detail']} ({summary})")
    else:
        for result in results:
            if result["chunks_written"] == 0:
                typer.echo(f"No changes: {result['source_id']!r} is already up to date.")
            else:
                typer.echo(f"Ingested {result['chunks_written']} chunk(s) for source {result['source_id']!r}.")
    return 0


def load_documents(
    path: Annotated[Path, typer.Argument(help="Directory containing corpus <name>.yaml/<name>.txt pairs")],
    chunk_size: Annotated[int, typer.Option("--chunk-size")] = 650,
    chunk_overlap: Annotated[int, typer.Option("--chunk-overlap")] = 100,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    settings = Settings()
    graph_store = KuzuGraphStore(settings.kuzu_db_path)
    vector_store = None if dry_run else ChromaVectorStore(settings.chroma_persist_dir)
    embedder = None if dry_run else OllamaEmbedder(model=settings.embedding_model, base_url=settings.ollama_base_url)

    exit_code = run_load_documents(
        path,
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=embedder,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        dry_run=dry_run,
        as_json=as_json,
    )
    raise typer.Exit(code=exit_code)
