# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""One query, run through the retrieval pipeline — the logic behind
`api/routes.py`'s query routes and the agent's `query_sign` tool. Every entry
point here returns the region shape (ADR-013). `MythrixError` is never caught
here; each caller handles it in whatever way suits its own transport."""

from __future__ import annotations

from datetime import UTC, datetime

from mythrix.core.embedding import Embedder
from mythrix.core.errors import AdhocQueryValidationError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import (
    AdhocTerm,
    GraphFacts,
    Interpretant,
    Manifestation,
    QueryDirective,
    RegionQueryResult,
    Segment,
    Sign,
    Tradition,
)
from mythrix.core.retrieval.pipeline import RetrievalPipeline
from mythrix.core.vector.store import ChromaVectorStore

_ADHOC_TRADITION = Tradition(id="adhoc", slug="adhoc", name="Ad-hoc", domain="adhoc")
_ADHOC_SIGN = Sign(id="adhoc", slug="adhoc", canonical_name="Ad-hoc query", sign_type="adhoc", semiotic_system="adhoc")


def query_regions(
    *,
    sign: str,
    tradition: str,
    graph_store: KuzuGraphStore,
    vector_store: ChromaVectorStore,
    embedder: Embedder,
    match_pool_size: int,
    min_score: float,
    region_window_size: int,
    region_min_interpretants: int,
) -> RegionQueryResult:
    """Region-centric retrieval (see `specs/retrieval/ranking.md`) — the query
    path `/api/query` runs."""
    graph_facts = graph_store.get_manifestation(sign, tradition)
    pipeline = RetrievalPipeline(
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=embedder,
        match_pool_size=match_pool_size,
        min_score=min_score,
        region_window_size=region_window_size,
        region_min_interpretants=region_min_interpretants,
    )
    return pipeline.retrieve_regions(graph_facts)


def _adhoc_interpretant(position: int, term: AdhocTerm) -> Interpretant:
    query = QueryDirective(directive=term.directive, as_token=term.value) if term.directive else None
    return Interpretant(id=f"adhoc-{position}", type="concept", value=term.value, position=position, query=query)


def execute_adhoc_query(
    *,
    terms: list[AdhocTerm],
    graph_store: KuzuGraphStore,
    vector_store: ChromaVectorStore,
    embedder: Embedder,
    match_pool_size: int,
    min_score: float,
    region_window_size: int,
    region_min_interpretants: int,
) -> RegionQueryResult:
    """Region-centric retrieval over a user-supplied, graph-independent term
    list (`specs/interfaces/agnostic-query.md` FR-AQ-09–12, ADR-010) —
    the ad-hoc counterpart to `query_regions`. Builds a synthetic `GraphFacts`
    from `terms` instead of resolving one from the graph store via
    `get_manifestation`, then runs the unmodified region-query pipeline —
    every matching/ranking requirement `query_regions` satisfies applies here
    identically. `graph_store` is still required and still read-only: the
    pipeline still calls it to hydrate a matched segment's `Source` for
    citation, even though this path never calls `get_manifestation`. The
    synthetic sign/tradition/manifestation carry sentinel `"adhoc"`
    identifiers so a result is never mistaken for curated Sign Graph content.
    """
    if not terms:
        raise AdhocQueryValidationError("An ad-hoc query needs at least one term.")

    manifestation = Manifestation(
        id="adhoc",
        sign_id=_ADHOC_SIGN.id,
        tradition=_ADHOC_TRADITION,
        display_name="Ad-hoc query",
        interpretants=tuple(_adhoc_interpretant(i, term) for i, term in enumerate(terms)),
        created_at=datetime.now(UTC),
    )
    graph_facts = GraphFacts(sign=_ADHOC_SIGN, manifestation=manifestation)

    pipeline = RetrievalPipeline(
        graph_store=graph_store,
        vector_store=vector_store,
        embedder=embedder,
        match_pool_size=match_pool_size,
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
