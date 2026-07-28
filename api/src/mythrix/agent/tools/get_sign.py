"""The `get_sign` tool."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.agent.tools._shared import _error, _render_graph_facts, _resolve_sign
from mythrix.core.bootstrap import Stores
from mythrix.core.errors import MythrixError


def build_get_sign_tool(stores: Stores):
    @tool
    def get_sign(sign: str, tradition: str | None = None) -> dict:
        """The tool for "tell me about X" / "what is X" / "what does X mean"
        requests. Retrieve one named sign's graph facts (e.g.
        sign="the-magician" or sign="The Magician" — matches either the
        slug or the display name): its canonical name, semiotic system,
        intrinsic properties, and — for a tradition — its interpretants,
        denotation, correspondences, and citations. This is a graph-facts
        lookup, not a corpus search — use query_sign instead only if the
        user explicitly asks for supporting passages, textual evidence, or
        convergence from the corpus. If the sign has exactly one tradition it
        is used automatically; if it has several and none is given, this
        returns the choices under needs_tradition instead of facts — ask the
        user which one, and once they answer (even a bare tradition name),
        call get_sign again with the same sign and that tradition;
        do not switch to query_sign for that follow-up."""
        summary = _resolve_sign(stores.graph_store.list_signs(), sign)
        if summary is None:
            return {"error": f"unknown sign {sign!r}"}
        if tradition is None:
            if len(summary.tradition_slugs) == 1:
                tradition = summary.tradition_slugs[0]
            else:
                return {
                    "needs_tradition": True,
                    "sign": summary.canonical_name,
                    "traditions": list(summary.tradition_slugs),
                }
        try:
            facts = stores.graph_store.get_manifestation(summary.slug, tradition)
        except MythrixError as exc:
            return _error(exc)
        return _render_graph_facts(facts)

    return get_sign
