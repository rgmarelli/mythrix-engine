"""`mythrix query`: the CLI surface for FR9/FR14/FR15/FR16.

`run_query` holds all the actual logic and returns a process exit code — the
Typer-decorated `query` command below is a thin wrapper that builds real
`KuzuGraphStore`/`ChromaVectorStore`/`OllamaEmbedder`/`OllamaSynthesizer`
instances from `Settings` and delegates. This split is what lets
`tests/unit/test_cli_query.py` call `run_query` directly with fakes, with no
Typer/subprocess machinery and no running Ollama needed for most cases.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

import typer

from mythrix.cli.formatting import render_facts_human, render_facts_json, render_result_human, render_result_json
from mythrix.core.config import Settings
from mythrix.core.embedding import Embedder, OllamaEmbedder
from mythrix.core.errors import CitationValidationError, MythrixError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.retrieval.pipeline import RetrievalPipeline
from mythrix.core.synthesis.chain import OllamaSynthesizer, Synthesizer
from mythrix.core.vector.store import ChromaVectorStore


def run_query(
    *,
    symbol: str,
    tradition: str,
    graph_store: KuzuGraphStore,
    vector_store: ChromaVectorStore,
    embedder: Embedder,
    synthesizer_factory: Callable[[], Synthesizer],
    top_k: int,
    min_score: float,
    facts_only: bool = False,
    as_json: bool = False,
    strict: bool = False,
) -> int:
    """Runs one query end-to-end and prints the result; returns the process
    exit code (0 = success). `synthesizer_factory` is only called when
    `facts_only` is `False`, so a facts-only query never needs a reachable
    *generation* model — it still needs a reachable *embedding* model, since
    retrieval embeds the query text for the Chroma similarity search either way.
    """
    try:
        graph_facts = graph_store.get_interpretation(symbol, tradition)

        pipeline = RetrievalPipeline(
            graph_store=graph_store, vector_store=vector_store, embedder=embedder, top_k=top_k, min_score=min_score
        )
        context = pipeline.retrieve(graph_facts)
    except MythrixError as exc:
        typer.echo(f"Error: {exc}", err=True)
        return 1

    if facts_only:
        typer.echo(render_facts_json(context) if as_json else render_facts_human(context))
        return 0

    try:
        result = synthesizer_factory().synthesize(context)
    except MythrixError as exc:
        typer.echo(f"Error: {exc}", err=True)
        return 1

    typer.echo(render_result_json(result) if as_json else render_result_human(result))

    if strict and not result.citation_markers_valid:
        typer.echo(f"Error: {CitationValidationError(result.invalid_markers)}", err=True)
        return 1
    return 0


def query(
    symbol: Annotated[str, typer.Option("--symbol", help="Symbol slug, as loaded via load-symbols")],
    tradition: Annotated[str, typer.Option("--tradition", help="Tradition slug, as loaded via load-symbols")],
    top_k: Annotated[int | None, typer.Option("--top-k", help="Override retrieval_top_k")] = None,
    facts_only: Annotated[bool, typer.Option("--facts-only", help="Skip LLM synthesis (FR14)")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Structured JSON output (FR16)")] = False,
    strict: Annotated[bool, typer.Option("--strict", help="Citation-validation failure is a hard error (FR15)")] = (
        False
    ),
) -> None:
    settings = Settings()
    graph_store = KuzuGraphStore(settings.kuzu_db_path)
    vector_store = ChromaVectorStore(settings.chroma_persist_dir)
    embedder = OllamaEmbedder(model=settings.embedding_model, base_url=settings.ollama_base_url)

    def synthesizer_factory() -> Synthesizer:
        return OllamaSynthesizer(
            generation_model=settings.generation_model or "",
            embedding_model=settings.embedding_model,
            base_url=settings.ollama_base_url,
        )

    exit_code = run_query(
        symbol=symbol,
        tradition=tradition,
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=embedder,
        synthesizer_factory=synthesizer_factory,
        top_k=top_k or settings.retrieval_top_k,
        min_score=settings.retrieval_min_score,
        facts_only=facts_only,
        as_json=as_json,
        strict=strict,
    )
    raise typer.Exit(code=exit_code)
