"""The `query_sign` tool."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.agent.tools._shared import _error, _render_regions, _resolve_sign, _resolve_tradition
from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings
from mythrix.core.errors import MythrixError
from mythrix.core.query_service import query_regions


def build_query_sign_tool(stores: Stores, settings: Settings):
    @tool
    def query_sign(
        sign: str,
        tradition: str,
        min_score: float | None = None,
    ) -> dict:
        """Retrieve ranked textual evidence regions (hotspots) for a sign in
        a tradition — corpus passages where the sign's interpretants converge,
        with citations. Use this only when the user explicitly asks for
        supporting evidence, passages, or convergence in the corpus (e.g.
        "what evidence supports X", "where does X converge in the text").
        For a general "tell me about X" / "what does X mean" request, use
        get_sign instead — including a reply that just names a tradition
        after get_sign asked which one to use. Relay the returned regions
        as retrieved — verbatim passage text, scores, and citations — without
        paraphrasing or adding your own interpretation of what a passage
        means; use summarize_passage for that, and only if the user asks."""
        summary = _resolve_sign(stores.graph_store.list_signs(), sign)
        if summary is None:
            return {"error": f"unknown sign {sign!r}"}
        resolved = _resolve_tradition(stores.graph_store.list_traditions(), tradition)
        if resolved is None:
            return {"error": f"unknown tradition {tradition!r}"}
        try:
            result = query_regions(
                sign=summary.slug,
                tradition=resolved.slug,
                graph_store=stores.graph_store,
                vector_store=stores.vector_store,
                embedder=stores.embedder,
                match_pool_size=settings.retrieval_match_pool_size,
                min_score=min_score if min_score is not None else settings.retrieval_min_score,
                region_window_size=settings.region_window_size,
                region_min_interpretants=settings.region_min_interpretants,
            )
        except MythrixError as exc:
            return _error(exc)
        return {
            "sign": summary.slug,
            "sign_name": summary.canonical_name,
            "tradition": resolved.slug,
            "tradition_name": resolved.name,
            **_render_regions(result),
        }

    return query_sign
