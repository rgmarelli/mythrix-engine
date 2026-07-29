"""The `query_adhoc` tool — node-only (ADR-015)."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.agent.tools._shared import _error, _render_regions
from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings
from mythrix.core.errors import MythrixError
from mythrix.core.models import AdhocTerm
from mythrix.core.query_service import execute_adhoc_query


def build_query_adhoc_tool(stores: Stores, settings: Settings):
    @tool
    def query_adhoc(terms: list[dict], limit: int) -> dict:
        """Retrieve ranked evidence regions for a user-supplied term list,
        with no sign or tradition involved. Reachable only from a
        deterministic node — it is deliberately absent from the model's own
        tool set, so an ad-hoc query is never run on the model's initiative
        (ADR-010, ADR-015)."""
        try:
            result = execute_adhoc_query(
                terms=[AdhocTerm(**term) for term in terms],
                graph_store=stores.graph_store,
                vector_store=stores.vector_store,
                embedder=stores.embedder,
                match_pool_size=settings.retrieval_match_pool_size,
                min_score=settings.retrieval_min_score,
                region_window_size=settings.region_window_size,
                region_min_interpretants=settings.region_min_interpretants,
            )
        except MythrixError as exc:
            return _error(exc)
        regions = _render_regions(result, include_segments=False)["regions"]
        return {"matched_count": len(regions), "regions": regions[:limit]}

    return query_adhoc
