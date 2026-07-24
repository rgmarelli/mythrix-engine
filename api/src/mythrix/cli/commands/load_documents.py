"""`mythrix load-documents`: wraps `document_loader.load_corpus_directory`
(FR-CO-01, FR-CO-04).

Auto-discovers every corpus source under `path` — each `<name>.yaml`
colocated with a `<name>.txt` of the same stem — registering the `Source`
from its own YAML (`id`/`domain`/`citation_label`) and ingesting its text.
No `--tradition`/`--domain`/`--source-slug` flags: a corpus document is never
assigned a tradition (FR-CO-02), and its id/domain are authored directly in its
own file, not repeated on the command line.

`--dry-run` only hashes each `.txt` and compares it to its `Source`'s
recorded `content_hash` (FR-CO-04) — it never constructs an embedder or vector
store, so it works even without a reachable Ollama daemon.
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
            typer.echo(f"{result['source_id']!r}: {result['status']} — {result['detail']}")
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
