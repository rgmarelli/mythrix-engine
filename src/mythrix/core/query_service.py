"""One query, run through the retrieval pipeline — the logic shared by the
CLI (`cli/commands/query.py::run_query`, via `execute_query`) and the API
(`api/routes.py`, via `stream_query`). Neither catches `MythrixError` here;
each caller handles it in whatever way suits its own transport."""

from __future__ import annotations

from collections.abc import Iterator

from mythrix.core.embedding import Embedder
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import ConceptCandidates, RetrievalContext
from mythrix.core.retrieval.pipeline import RetrievalPipeline
from mythrix.core.vector.store import ChromaVectorStore


def execute_query(
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
) -> RetrievalContext:
    graph_facts = graph_store.get_manifestation(symbol, tradition)
    pipeline = RetrievalPipeline(
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=embedder,
        top_k=top_k,
        match_pool_size=match_pool_size,
        merge_top_k=merge_top_k,
        min_score=min_score,
    )
    return pipeline.retrieve(graph_facts)


def stream_query(
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
) -> Iterator[tuple[str, dict]]:
    """Yields `(event_type, payload)` pairs: `"graph_facts"` first — the
    `KuzuGraphStore.get_manifestation` call that can raise
    `SignNotFoundError`/`TraditionNotFoundError`/`ManifestationNotFoundError`
    runs before this generator's first `yield`, so a caller that primes it
    with one `next()` call sees that error there, not mid-iteration — then
    one `"concept_candidates"`/`"pair_candidates"` pair per item from
    `RetrievalPipeline.iter_candidates` (where `ModelUnavailableError`/
    `ModelRequestError` can still surface, once the embedder is called)."""
    graph_facts = graph_store.get_manifestation(symbol, tradition)
    yield "graph_facts", graph_facts.model_dump(mode="json")

    pipeline = RetrievalPipeline(
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=embedder,
        top_k=top_k,
        match_pool_size=match_pool_size,
        merge_top_k=merge_top_k,
        min_score=min_score,
    )
    for item in pipeline.iter_candidates(graph_facts):
        event_type = "concept_candidates" if isinstance(item, ConceptCandidates) else "pair_candidates"
        yield event_type, item.model_dump(mode="json")
