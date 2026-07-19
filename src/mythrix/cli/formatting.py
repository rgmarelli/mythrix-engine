"""Human-readable and JSON renderers for CLI output (FR13, FR16).

Reuses `synthesis/prompts.py`'s `render_graph_facts_block`/`render_passages_block`
for the human-readable References section — the same rendering the model
itself was shown, so what a researcher reads matches exactly what was cited.
"""

from __future__ import annotations

import json

from mythrix.core.models import GraphFacts, InterpretationResult, RetrievalContext, RetrievedPassage
from mythrix.core.synthesis.prompts import graph_fact_lines, render_graph_facts_block, render_passages_block

_HUMAN_PASSAGE_PREVIEW_CHARS = 500


def _graph_facts_payload(graph_facts: GraphFacts) -> dict:
    markers = {f"G{i + 1}": line for i, line in enumerate(graph_fact_lines(graph_facts))}
    return {
        "markers": markers,
        "symbol": graph_facts.symbol.model_dump(mode="json"),
        "interpretation": graph_facts.interpretation.model_dump(mode="json"),
    }


def _passages_payload(passages: tuple[RetrievedPassage, ...]) -> dict:
    markers = {f"S{i + 1}": passage.text for i, passage in enumerate(passages)}
    return {"markers": markers, "items": [passage.model_dump(mode="json") for passage in passages]}


def render_facts_human(context: RetrievalContext) -> str:
    """`--facts-only` human-readable output: just the retrieved facts/passages,
    no narrative (FR14 — no LLM was invoked to produce this)."""
    return "\n\n".join(
        [
            render_graph_facts_block(context.graph_facts),
            render_passages_block(context.passages, max_chars=_HUMAN_PASSAGE_PREVIEW_CHARS),
        ]
    )


def render_facts_json(context: RetrievalContext) -> str:
    """`--facts-only --json` output — the evidentiary chain (FR16) without a
    narrative or model identifiers, since none were used."""
    payload = {
        "graph_facts": _graph_facts_payload(context.graph_facts),
        "passages": _passages_payload(context.passages),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def render_result_human(result: InterpretationResult) -> str:
    interpretation = result.context.graph_facts.interpretation
    header = f"{interpretation.display_name} ({interpretation.tradition.name})"
    citation_status = (
        "yes" if result.citation_markers_valid else f"NO — invalid marker(s): {', '.join(result.invalid_markers)}"
    )
    sections = [
        header,
        "=" * len(header),
        result.narrative,
        "",
        "References:",
        render_graph_facts_block(result.context.graph_facts),
        render_passages_block(result.context.passages, max_chars=_HUMAN_PASSAGE_PREVIEW_CHARS),
        "",
        f"Generation model: {result.generation_model} | Embedding model: {result.embedding_model} | "
        f"Generated at: {result.generated_at.isoformat()}",
        f"Citations valid: {citation_status}",
    ]
    return "\n".join(sections)


def render_result_json(result: InterpretationResult) -> str:
    """Full evidentiary chain (FR16): graph fact/passage identifiers and
    verbatim text, plus the embedding/generation model identifiers and
    timestamp used, so a result is reproducible and auditable later even if
    the corpus or models change."""
    payload = {
        "narrative": result.narrative,
        "generation_model": result.generation_model,
        "embedding_model": result.embedding_model,
        "citation_markers_valid": result.citation_markers_valid,
        "invalid_markers": list(result.invalid_markers),
        "generated_at": result.generated_at.isoformat(),
        "graph_facts": _graph_facts_payload(result.context.graph_facts),
        "passages": _passages_payload(result.context.passages),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
