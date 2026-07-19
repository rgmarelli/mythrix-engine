"""`mythrix query`: the CLI surface for FR9/FR13/FR16/FR24/FR27-FR29.

`run_query` holds all the actual logic and returns a process exit code — the
Typer-decorated `query` command below is a thin wrapper that builds real
`KuzuGraphStore`/`ChromaVectorStore`/`OllamaEmbedder` instances from
`Settings` and delegates. This split is what lets `tests/unit/test_cli_query.py`
call `run_query` directly with fakes, with no Typer/subprocess machinery and
no running Kùzu/Chroma needed for most cases.

Per FR29, no generation model is ever constructed on this path — retrieval
needs only the embedding model, so a query returns the complete result
whether or not a local generation model is installed.
"""

from __future__ import annotations

from typing import Annotated

import typer

from mythrix.cli.formatting import render_facts_human, render_facts_json
from mythrix.core.config import Settings
from mythrix.core.embedding import Embedder, OllamaEmbedder
from mythrix.core.errors import MythrixError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.retrieval.pipeline import RetrievalPipeline
from mythrix.core.vector.store import ChromaVectorStore


def run_query(
    *,
    symbol: str,
    tradition: str,
    graph_store: KuzuGraphStore,
    vector_store: ChromaVectorStore,
    embedder: Embedder,
    top_k: int,
    match_pool_size: int,
    merge_top_k: int,
    min_score: float,
    as_json: bool = False,
) -> int:
    """Runs one query end-to-end and prints the result; returns the process
    exit code (0 = success). Needs a reachable embedding model (retrieval
    embeds the query text for the Chroma similarity search) but never a
    generation model (FR29)."""
    try:
        graph_facts = graph_store.get_interpretation(symbol, tradition)

        pipeline = RetrievalPipeline(
            graph_store=graph_store,
            vector_store=vector_store,
            embedder=embedder,
            top_k=top_k,
            match_pool_size=match_pool_size,
            merge_top_k=merge_top_k,
            min_score=min_score,
        )
        context = pipeline.retrieve(graph_facts)
    except MythrixError as exc:
        typer.echo(f"Error: {exc}", err=True)
        return 1

    typer.echo(render_facts_json(context) if as_json else render_facts_human(context))
    return 0


def query(
    symbol: Annotated[str, typer.Option("--symbol", help="Symbol slug, as loaded via load-symbols")],
    tradition: Annotated[str, typer.Option("--tradition", help="Tradition slug, as loaded via load-symbols")],
    top_k: Annotated[int | None, typer.Option("--top-k", help="Override retrieval_top_k")] = None,
    match_pool: Annotated[
        int | None,
        typer.Option("--match-pool", help="Override retrieval_match_pool_size — depth searched for pair convergence"),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Structured JSON output (FR16)")] = False,
) -> None:
    settings = Settings()
    graph_store = KuzuGraphStore(settings.kuzu_db_path)
    vector_store = ChromaVectorStore(settings.chroma_persist_dir)
    embedder = OllamaEmbedder(model=settings.embedding_model, base_url=settings.ollama_base_url)

    exit_code = run_query(
        symbol=symbol,
        tradition=tradition,
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=embedder,
        top_k=top_k or settings.retrieval_top_k,
        match_pool_size=match_pool or settings.retrieval_match_pool_size,
        merge_top_k=settings.merge_top_k,
        min_score=settings.retrieval_min_score,
        as_json=as_json,
    )
    raise typer.Exit(code=exit_code)
