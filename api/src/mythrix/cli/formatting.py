"""Human-readable and JSON renderers for CLI output (FR-RT-05, FR-RT-06, FR-RT-07, FR-RT-08).

Reuses `synthesis/prompts.py`'s `render_graph_facts_block`/`render_passages_block`
verbatim for the per-concept sections — the same rendering a future
conversational agent would be shown, so what a researcher reads today matches
what would be cited later.

Per FR-RT-10 the query path produces no synthesized narrative — output is
retrieved evidence only: graph facts, one section per concept (FR-RT-07), and one
section per concept-pair convergence (FR-RT-08), each carrying full verbatim
passage text and attribution (FR-RT-05).
"""

from __future__ import annotations

import json

from mythrix.core.models import ConceptMatchScore, ConceptPairCandidates, RetrievalContext, RetrievedPassage
from mythrix.core.serialization import facts_json_payload
from mythrix.core.synthesis.prompts import render_graph_facts_block, render_passages_block

_HUMAN_PASSAGE_PREVIEW_CHARS = 500


def _render_candidates_block(concept: str, passages: tuple[RetrievedPassage, ...], *, max_chars: int | None) -> str:
    """Like `render_passages_block`, but headed by the concept these
    passages were retrieved for (FR-RT-07) instead of a generic `PASSAGES` label
    — `render_passages_block`'s own `[S#]` numbering/body is reused verbatim,
    only its header line is swapped."""
    _, _, body = render_passages_block(passages, max_chars=max_chars).partition("\n")
    return f'CANDIDATES — "{concept}"\n{body}'


def _render_match_component(match: ConceptMatchScore) -> str:
    """An exact-value match (FR-RT-09) carries no meaningful score — it's a
    guarantee of containment, not a similarity judgment — so it's shown by
    name alone; a semantic match shows its own similarity score."""
    return match.concept if match.exact_value else f"{match.concept} {match.score:.2f}"


def _render_pair_block(pair: ConceptPairCandidates, *, max_chars: int | None) -> str:
    """Concept-pair convergence (FR-RT-08, FR-RT-09): headed like `_render_candidates_block`
    but by the pair's members, and each candidate shows its combined score
    *alongside* the per-concept components it was derived from — the verdict
    and its inputs together, since the combined score alone can't distinguish
    a genuine intersection from a lopsided match that merely reached the
    other concept's deep matching pool (see retrieval/pipeline.py)."""
    label = ", ".join(pair.concepts)
    if not pair.candidates:
        return f"CANDIDATES — [{label}]\n(none retrieved)"
    lines = []
    for i, candidate in enumerate(pair.candidates):
        passage = candidate.passage
        attribution = passage.source.citation_label or f"{passage.source.title}, {passage.source.author}"
        if passage.locator:
            attribution += f", {passage.locator}"
        components = " · ".join(_render_match_component(match) for match in candidate.matches)
        text = passage.text
        if max_chars is not None and len(text) > max_chars:
            text = text[:max_chars].rstrip() + "… [truncated for display — full text in --json]"
        lines.append(
            f"[S{i + 1}] Signs: {label}   {candidate.combined_score:.2f}  ({components})\n"
            f'     ({attribution}): "{text}"'
        )
    return f"CANDIDATES — [{label}]\n" + "\n".join(lines)


def render_facts_human(context: RetrievalContext) -> str:
    """Human-readable query output: retrieved graph facts, per-concept
    candidate passages (FR-RT-07), and concept-pair convergences (FR-RT-08) — no
    synthesized narrative, since the query path invokes no generation model
    (FR-RT-10)."""
    sections = [render_graph_facts_block(context.graph_facts)]
    if context.concept_candidates:
        sections += [
            _render_candidates_block(candidates.concept, candidates.passages, max_chars=_HUMAN_PASSAGE_PREVIEW_CHARS)
            for candidates in context.concept_candidates
        ]
    else:
        sections.append("CANDIDATES\n(none retrieved)")
    sections += [_render_pair_block(pair, max_chars=_HUMAN_PASSAGE_PREVIEW_CHARS) for pair in context.pair_candidates]
    return "\n\n".join(sections)


def render_facts_json(context: RetrievalContext) -> str:
    """`--json` output (FR-RT-06) — `facts_json_payload` (`core/serialization.py`)
    builds the payload; this just serializes it."""
    return json.dumps(facts_json_payload(context), indent=2, ensure_ascii=False)
