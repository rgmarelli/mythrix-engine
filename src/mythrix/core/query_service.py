"""One query, run through the retrieval pipeline — the logic shared by the
CLI (`cli/commands/query.py::run_query`, via `execute_query`) and the API
(`api/routes.py`, via `query_fragments`). Neither catches `MythrixError` here;
each caller handles it in whatever way suits its own transport."""

from __future__ import annotations

from mythrix.core.embedding import Embedder
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import FragmentQueryResult, RetrievalContext
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


def query_fragments(
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
) -> FragmentQueryResult:
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
    return pipeline.retrieve_fragments(graph_facts)
