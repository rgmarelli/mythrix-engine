# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The `get_sign` tool."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.agent.tools._shared import (
    _error,
    _render_graph_facts,
    _resolve_sign,
    _resolve_tradition,
    _unknown_sign_error,
)
from mythrix.core.bootstrap import Stores
from mythrix.core.errors import MythrixError


def build_get_sign_tool(stores: Stores):
    @tool
    def get_sign(sign: str, tradition: str | None = None, semiotic_system: str | None = None) -> dict:
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
        do not switch to query_sign for that follow-up. Pass semiotic_system
        (its slug, e.g. "tarot") when the conversation has already
        established which system to search, to resolve sign against only
        that system's signs.

        In the result, `sign` and `tradition` identify the entities and
        `sign_name`/`tradition_name` are how to refer to them in a reply."""
        signs = stores.graph_store.list_signs()
        summary = _resolve_sign(signs, sign, semiotic_system)
        if summary is None:
            resolved_tradition = (
                _resolve_tradition(stores.graph_store.list_traditions(), tradition) if tradition is not None else None
            )
            return _unknown_sign_error(signs, sign, resolved_tradition, semiotic_system)
        if tradition is None:
            if len(summary.tradition_slugs) == 1:
                tradition_slug = summary.tradition_slugs[0]
            else:
                names = {t.slug: t.name for t in stores.graph_store.list_traditions()}
                return {
                    "needs_tradition": True,
                    "sign": summary.slug,
                    "sign_name": summary.canonical_name,
                    "traditions": [{"slug": slug, "name": names.get(slug, slug)} for slug in summary.tradition_slugs],
                }
        else:
            resolved = _resolve_tradition(stores.graph_store.list_traditions(), tradition)
            if resolved is None:
                return {"error": f"unknown tradition {tradition!r}"}
            tradition_slug = resolved.slug
        try:
            facts = stores.graph_store.get_manifestation(summary.slug, tradition_slug)
        except MythrixError as exc:
            return _error(exc)
        return _render_graph_facts(facts)

    return get_sign
