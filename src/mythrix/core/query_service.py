"""One query, run through the retrieval pipeline — the logic shared by the
CLI (`cli/commands/query.py::run_query`, via `execute_query`) and the API
(`api/routes.py`, via `query_regions`). Neither catches `MythrixError` here;
each caller handles it in whatever way suits its own transport."""

from __future__ import annotations

from mythrix.core.embedding import Embedder
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import RegionQueryResult, RetrievalContext, Segment
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


def query_regions(
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
    region_window_size: int,
    region_min_interpretants: int,
) -> RegionQueryResult:
    """Region-centric retrieval (`convergence-rollup-retrieval`) — the query
    path `/api/query` runs."""
    graph_facts = graph_store.get_manifestation(symbol, tradition)
    pipeline = RetrievalPipeline(
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=embedder,
        top_k=top_k,
        match_pool_size=match_pool_size,
        merge_top_k=merge_top_k,
        min_score=min_score,
        region_window_size=region_window_size,
        region_min_interpretants=region_min_interpretants,
    )
    return pipeline.retrieve_regions(graph_facts)


def fetch_source_segments(
    *,
    source_id: str,
    start_ordinal: int,
    end_ordinal: int,
    graph_store: KuzuGraphStore,
    vector_store: ChromaVectorStore,
) -> tuple[Segment, ...]:
    """A contiguous ordinal range of one source's segments, verbatim — the
    coordinate lookup the web viewer's Add Context action runs
    (`hotspot-context-expansion`), not a similarity search: no embedding
    model is invoked.

    `graph_store.get_source` is called for its `SourceNotFoundError` alone
    (unused otherwise) — an unknown `source_id` fails with a real 404 rather
    than a silently empty result.
    """
    graph_store.get_source(source_id)
    chunks = vector_store.get_segments(source_id, start_ordinal=start_ordinal, end_ordinal=end_ordinal)
    return tuple(
        Segment(ordinal=chunk.ordinal, locator=chunk.locator, text=chunk.text, section=chunk.section)
        for chunk in chunks
    )
