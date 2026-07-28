"""Rendering and resolution helpers shared by more than one tool module."""

from __future__ import annotations

from mythrix.core.errors import MythrixError
from mythrix.core.models import GraphFacts, RegionQueryResult


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
