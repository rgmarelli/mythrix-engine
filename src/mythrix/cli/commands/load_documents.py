"""`mythrix load-documents`: wraps `document_loader` (FR6, FR23).

The `Tradition`'s `domain` is looked up from the graph rather than requiring a
redundant `--domain` flag — a tradition already declares which domain it
belongs to (via `load-symbols`), so asking a curator to repeat it here would
just be another place the two could drift out of sync.

`--dry-run` only hashes the file and compares it to the `Source`'s recorded
`content_hash` (FR23) — it never constructs an embedder or vector store, so it
works even without a reachable Ollama daemon.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated

import typer

from mythrix.core.config import Settings
from mythrix.core.embedding import OllamaEmbedder
from mythrix.core.errors import MythrixError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.loaders.document_loader import load_document
from mythrix.core.vector.store import ChromaVectorStore


def _dry_run_status(path: Path, *, graph_store: KuzuGraphStore, source_id: str) -> tuple[str, str]:
    source = graph_store.get_source(source_id)
    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if content_hash == source.content_hash:
        return "unchanged", "no-op — file matches what's already ingested"
    if source.content_hash:
        return "changed", "would replace this source's existing chunks"
    return "new", "would ingest for the first time"


def run_load_documents(
    path: Path,
    *,
    source_id: str,
    tradition_slug: str,
    graph_store: KuzuGraphStore,
    vector_store: ChromaVectorStore | None,
    embedder: object | None,
    chunk_size: int,
    chunk_overlap: int,
    dry_run: bool,
    as_json: bool,
) -> int:
    try:
        tradition = graph_store.get_tradition(tradition_slug)
        if dry_run:
            status, detail = _dry_run_status(path, graph_store=graph_store, source_id=source_id)
            result = {"dry_run": True, "source_id": source_id, "status": status, "detail": detail}
        else:
            chunks_written = load_document(
                path,
                source_id=source_id,
                tradition_slug=tradition_slug,
                domain=tradition.domain,
                graph_store=graph_store,
                vector_store=vector_store,
                embedder=embedder,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            result = {"dry_run": False, "source_id": source_id, "chunks_written": chunks_written}
    except MythrixError as exc:
        typer.echo(f"Error: {exc}", err=True)
        return 1

    if as_json:
        typer.echo(json.dumps(result, indent=2))
    elif dry_run:
        typer.echo(f"{source_id!r}: {result['status']} — {result['detail']}")
    elif result["chunks_written"] == 0:
        typer.echo(f"No changes: {source_id!r} is already up to date.")
    else:
        typer.echo(f"Ingested {result['chunks_written']} chunk(s) for source {source_id!r}.")
    return 0


def load_documents(
    path: Annotated[Path, typer.Argument(help="Source text file to ingest")],
    tradition: Annotated[str, typer.Option("--tradition", help="Tradition slug this document belongs to")],
    source_slug: Annotated[str | None, typer.Option("--source-slug", help="Defaults to the file's stem")] = None,
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
        source_id=source_slug or path.stem,
        tradition_slug=tradition,
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=embedder,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        dry_run=dry_run,
        as_json=as_json,
    )
    raise typer.Exit(code=exit_code)
