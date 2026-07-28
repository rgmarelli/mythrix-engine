"""The agent's fixed, read-only tool set (specs/interfaces/agent.md FR-AG-03, FR-AG-04) — every
tool is a thin wrapper over an existing Mythrix service function; none of this
module implements retrieval, graph, embedding, or synthesis logic of its own.

`build_tools` closes over an already-built `Stores`, `Settings`, and
`ChatClient` (constructed once by `api/dependencies.py`) instead of holding
module-level globals, so the tool set is trivially fakeable in tests and is
rebuilt fresh per process rather than shared mutable state.

Each tool returns compact, JSON-serializable data (dicts / lists of dicts) —
never prose — so the LLM relays cited evidence rather than inventing it
(FR-AG-06). A `MythrixError` raised while a tool runs (unknown sign/tradition/source,
an unreachable model) is caught here and turned into a structured `{"error":
...}` result instead of propagating, so a bad tool call becomes a recoverable
turn (FR-AG-11) rather than crashing the graph.
"""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.agent.prompts import render_passage_summary_prompt
from mythrix.core.bootstrap import Stores
from mythrix.core.chat import ChatClient
from mythrix.core.config import Settings
from mythrix.core.errors import MythrixError
from mythrix.core.models import GraphFacts, RegionQueryResult
from mythrix.core.query_service import fetch_source_segments, query_regions


def _error(exc: MythrixError) -> dict:
    return {"error": str(exc)}


def _resolve_sign(signs, sign: str):  # noqa: ANN001, ANN201 - SignSummary | None; avoids importing it just for this
    """Matches `sign` against a sign's slug or canonical name,
    case/whitespace-insensitive. `get_sign`/`query_sign` take `sign`
    straight from the model's own wording of the user's request (e.g. "The
    Magician") before any tool has ever surfaced the real slug
    ("the-magician") — matching by slug alone would fail on exactly the
    phrasing the spec's own example uses."""
    normalized = sign.strip().casefold()
    return next(
        (s for s in signs if s.slug.casefold() == normalized or s.canonical_name.casefold() == normalized), None
    )


def _render_graph_facts(facts: GraphFacts) -> dict:
    """Compact rendering of one sign's graph facts — the `get_sign`
    counterpart to `_render_regions`, built from the same `GraphFacts`
    `KuzuGraphStore.get_manifestation` already returns."""
    sign, manifestation = facts.sign, facts.manifestation
    return {
        "sign": sign.canonical_name,
        "semiotic_system": sign.semiotic_system,
        "sign_type": sign.sign_type,
        "properties": [{"key": p.key, "value": p.value} for p in sign.properties],
        "tradition": manifestation.tradition.name,
        "display_name": manifestation.display_name,
        "denotation": manifestation.denotation,
        "interpretants": [{"type": i.type, "value": i.value} for i in manifestation.interpretants],
        "correspondences": [
            {
                "relationship": ii.relationship,
                "target_sign": ii.target_sign.canonical_name,
                "according_to": ii.according_to.name,
                "description": ii.description,
            }
            for ii in sign.intersemiotic_interpretants
        ],
        "citations": [
            {"source": c.source.citation_label or c.source.title, "locator": c.locator} for c in manifestation.citations
        ],
    }


def _render_regions(result: RegionQueryResult) -> dict:
    """Compact rendering of a region query result — mirrors the shape
    `GET /api/query` returns, trimmed to what the agent needs to relay:
    ranked regions with their matches, verbatim segments, and citations."""
    return {
        "regions": [
            {
                "region_id": region.region_id,
                "source": region.source.citation_label or region.source.title,
                "source_id": region.source.id,
                "locator": region.locator,
                "score": region.score,
                "convergence_count": region.convergence_count,
                "matches": [
                    {
                        "interpretant": match.interpretant,
                        "kind": match.kind,
                        "score": match.score,
                        "segment_ordinal": match.segment_ordinal,
                    }
                    for match in region.matches
                ],
                "segments": [
                    {"ordinal": seg.ordinal, "locator": seg.locator, "section": seg.section, "text": seg.text}
                    for seg in region.segments
                ],
            }
            for region in result.regions
        ]
    }


def build_tools(stores: Stores, settings: Settings, chat_client: ChatClient) -> list:
    """Returns the seven read-only tools the agent may call
    (specs/interfaces/agent.md FR-AG-03). The registered set contains no `upsert_*`, `load_*`, or reload
    operation — read-only is a structural property of this list, not a
    runtime check (FR-AG-04)."""

    @tool
    def list_semiotic_systems() -> list[str]:
        """List the available semiotic systems (top-level sign domains,
        e.g. "tarot", "hebrew_alef_bet"). Call this and ask the user which one
        to use before listing signs/traditions or getting/querying a sign
        whenever the semiotic system is ambiguous."""
        return list(stores.graph_store.list_semiotic_systems())

    @tool
    def list_traditions(semiotic_system: str | None = None) -> list[dict]:
        """List available traditions. If semiotic_system is given, only
        traditions that have at least one sign manifested in that system."""
        traditions = stores.graph_store.list_traditions()
        if semiotic_system is None:
            return [{"slug": t.slug, "name": t.name} for t in traditions]
        scoped_slugs = {
            tradition_slug
            for sign in stores.graph_store.list_signs()
            if sign.semiotic_system == semiotic_system
            for tradition_slug in sign.tradition_slugs
        }
        return [{"slug": t.slug, "name": t.name} for t in traditions if t.slug in scoped_slugs]

    @tool
    def list_signs(semiotic_system: str | None = None) -> list[dict]:
        """List available signs, optionally scoped to one semiotic
        system. Each entry includes the traditions the sign is manifested in."""
        return [
            {
                "slug": sign.slug,
                "name": sign.canonical_name,
                "semiotic_system": sign.semiotic_system,
                "traditions": list(sign.tradition_slugs),
            }
            for sign in stores.graph_store.list_signs()
            if semiotic_system is None or sign.semiotic_system == semiotic_system
        ]

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
        try:
            result = query_regions(
                sign=summary.slug,
                tradition=tradition,
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
        return _render_regions(result)

    @tool
    def fetch_segments(source_id: str, start_ordinal: int, end_ordinal: int) -> list[dict]:
        """Read a contiguous ordinal range of one source's segments verbatim,
        by structural coordinate — no similarity search. Use this to show the
        text surrounding a region a query returned."""
        try:
            segments = fetch_source_segments(
                source_id=source_id,
                start_ordinal=start_ordinal,
                end_ordinal=end_ordinal,
                graph_store=stores.graph_store,
                vector_store=stores.vector_store,
            )
        except MythrixError as exc:
            return [_error(exc)]
        return [
            {"ordinal": seg.ordinal, "locator": seg.locator, "section": seg.section, "text": seg.text}
            for seg in segments
        ]

    @tool
    def summarize_passage(passage_text: str, concepts: list[str]) -> dict:
        """Produce a single-turn summary of an already-retrieved passage,
        scoped to the given interpretant concepts, using the generation
        model. Only call this on text a previous tool call actually returned."""
        try:
            summary = chat_client.invoke(render_passage_summary_prompt(passage_text, tuple(concepts)))
        except MythrixError as exc:
            return _error(exc)
        return {"summary": summary}

    return [
        list_semiotic_systems,
        list_traditions,
        list_signs,
        get_sign,
        query_sign,
        fetch_segments,
        summarize_passage,
    ]
