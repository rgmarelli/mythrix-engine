# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Rendering and resolution helpers shared by more than one tool module."""

from __future__ import annotations

from uuid import uuid4

from mythrix.core.chat import ChatClient
from mythrix.core.errors import MythrixError
from mythrix.core.models import GraphFacts, RegionQueryResult, Tradition


def _error(exc: MythrixError) -> dict:
    return {"error": str(exc)}


def _new_grounding_id(prefix: str) -> str:
    """An opaque, independently-generated citation marker id (ADR-022) — not
    derived from position or a shared counter, so a model cannot produce a
    valid-looking marker without having actually seen this exact id in a tool
    result this turn."""
    return f"{prefix}{uuid4().hex[:6]}"


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


def _resolve_sign(signs, sign: str, semiotic_system: str | None = None):  # noqa: ANN001, ANN201 - SignSummary | None; avoids importing it just for this
    # Optionally scoped to one semiotic_system first, then resolved by exact
    # slug, then exact name, then substring match — checked in that order so
    # an exact match is never shadowed by an unrelated fuzzy one (ADR-024).
    normalized = sign.strip().casefold()
    if not normalized:
        return None

    exact_slug, exact_name, fuzzy = [], [], []
    for s in signs:
        if semiotic_system is not None and s.semiotic_system != semiotic_system:
            continue
        slug, name = s.slug.casefold(), s.canonical_name.casefold()
        if slug == normalized:
            exact_slug.append(s)
        elif name == normalized:
            exact_name.append(s)
        elif normalized in name or normalized in slug or slug in normalized or name in normalized:
            fuzzy.append(s)

    for tier in (exact_slug, exact_name, fuzzy):
        if tier:
            return tier[0] if len(tier) == 1 else None
    return None


def _unknown_sign_error(signs, sign: str, tradition: Tradition | None, semiotic_system: str | None = None) -> dict:  # noqa: ANN001 - see _resolve_sign
    """The `{"error": ...}` `get_sign`/`query_sign` return when
    `_resolve_sign` finds no single match — names the signs the model could
    retry with instead of leaving it to guess, scoped to `tradition` and/or
    `semiotic_system` when either was already established (a narrower list is
    more useful to retry with than every sign in the graph)."""
    candidates = [
        s
        for s in signs
        if (tradition is None or tradition.slug in s.tradition_slugs)
        and (semiotic_system is None or s.semiotic_system == semiotic_system)
    ]
    names = ", ".join(sorted(s.canonical_name for s in candidates))
    scope = f" in {tradition.name}" if tradition is not None else ""
    return {"error": f"unknown sign {sign!r}. Available signs{scope}: {names}."}


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
            {
                "source": c.source.citation_label or c.source.title,
                "locator": c.locator,
                "grounding_id": _new_grounding_id("G"),
            }
            for c in manifestation.citations
        ],
    }


def _render_regions(result: RegionQueryResult) -> dict:
    """Compact rendering of a region query result for the agent to relay:
    ranked regions with their verbatim segments and citations. Not shared
    with `GET /api/query`'s own `RegionQueryResult` rendering — this one is
    scoped to exactly what `query_sign`'s docstring asks the model to relay
    (verbatim text, scores, and citations), nothing the model can act on
    further.

    Deliberately omits `region.region_id` (the model has no tool that
    accepts one — `read_region` is `node_tools`-only, ADR-015 — and it read
    enough like a citation, `"<source>::<start>-<end>"`, that a real model
    echoed it as one instead of a segment's actual `grounding_id`) and
    `region.matches` (per-interpretant ranking detail — a second `score`
    field one level down from the region's own, and a `segment_ordinal`
    that only repeats each segment's own `ordinal`; not something the
    docstring asks the model to relay, and not actionable by any tool)."""
    return {
        "regions": [
            {
                "source": region.source.citation_label or region.source.title,
                "source_id": region.source.id,
                "locator": region.locator,
                "score": region.score,
                "convergence_count": region.convergence_count,
                "segments": [
                    {
                        "ordinal": seg.ordinal,
                        "locator": seg.locator,
                        "section": seg.section,
                        "text": seg.text,
                        "grounding_id": _new_grounding_id("S"),
                    }
                    for seg in region.segments
                ],
            }
            for region in result.regions
        ]
    }
