"""Rendering and resolution helpers shared by more than one tool module."""

from __future__ import annotations

from mythrix.core.chat import ChatClient
from mythrix.core.errors import MythrixError
from mythrix.core.models import GraphFacts, RegionQueryResult, Tradition


def _error(exc: MythrixError) -> dict:
    return {"error": str(exc)}


def _generated(chat_client: ChatClient, prompt: str, key: str) -> dict:
    """One generation call rendered as a tool result: the model's text under
    `key`, or the `{"error": ...}` mapping every tool shares (FR-AG-11).

    The single place a tool invokes the narrow `ChatClient`. Each generative
    tool differs only in the prompt it renders and the key it returns under —
    sharing the prompt too would couple commands whose instructions genuinely
    differ."""
    try:
        return {key: chat_client.invoke(prompt)}
    except MythrixError as exc:
        return _error(exc)


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


def _resolve_tradition(traditions: tuple[Tradition, ...], tradition: str) -> Tradition | None:
    """Matches `tradition` against a tradition's slug or name,
    case/whitespace-insensitive — the tradition counterpart to
    `_resolve_sign`, and needed for the same reason: a request names its
    tradition in the user's own words ("Tarot de Marseille") before any tool
    has surfaced the slug ("marseille"), and the two are unrelated strings.
    Resolving here keeps display names out of the store, which accepts slugs
    only (ADR-014)."""
    normalized = tradition.strip().casefold()
    return next((t for t in traditions if t.slug.casefold() == normalized or t.name.casefold() == normalized), None)


def _render_graph_facts(facts: GraphFacts) -> dict:
    """Compact rendering of one sign's graph facts — the `get_sign`
    counterpart to `_render_regions`, built from the same `GraphFacts`
    `KuzuGraphStore.get_manifestation` already returns.

    A key naming an entity carries that entity's slug; its `*_name` companion
    carries the display name (ADR-014). `display_name` is not one of those
    pairs — it is the manifestation's tradition-scoped name ("Le Bateleur"),
    a different fact from the sign's own `sign_name` ("The Magician")."""
    sign, manifestation = facts.sign, facts.manifestation
    return {
        "sign": sign.slug,
        "sign_name": sign.canonical_name,
        "semiotic_system": sign.semiotic_system,
        "sign_type": sign.sign_type,
        "properties": [{"key": p.key, "value": p.value} for p in sign.properties],
        "tradition": manifestation.tradition.slug,
        "tradition_name": manifestation.tradition.name,
        "display_name": manifestation.display_name,
        "denotation": manifestation.denotation,
        "interpretants": [{"type": i.type, "value": i.value} for i in manifestation.interpretants],
        "correspondences": [
            {
                "relationship": ii.relationship,
                "target_sign": ii.target_sign.slug,
                "target_sign_name": ii.target_sign.canonical_name,
                "according_to": ii.according_to.slug,
                "according_to_name": ii.according_to.name,
                "description": ii.description,
            }
            for ii in sign.intersemiotic_interpretants
        ],
        "citations": [
            {"source": c.source.citation_label or c.source.title, "locator": c.locator} for c in manifestation.citations
        ],
    }


def _render_regions(result: RegionQueryResult, *, include_segments: bool = True) -> dict:
    """Compact rendering of a region query result — mirrors the shape
    `GET /api/query` returns, trimmed to what the agent needs to relay:
    ranked regions with their matches, verbatim segments, and citations.

    `include_segments=False` drops the passage text, leaving region identity,
    locator and score. For a caller that re-reads each region's *full
    contiguous* range by structural coordinate, the embedded segments are the
    wrong text anyway — a region carries only its match-carrying ordinals
    (FR-DS-29)."""
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
                **(
                    {
                        "segments": [
                            {"ordinal": seg.ordinal, "locator": seg.locator, "section": seg.section, "text": seg.text}
                            for seg in region.segments
                        ]
                    }
                    if include_segments
                    else {}
                ),
            }
            for region in result.regions
        ]
    }
