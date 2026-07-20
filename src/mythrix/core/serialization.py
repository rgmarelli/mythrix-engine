"""`--json` output payload shape for `RetrievalContext` (FR16) — shared by
`cli/formatting.py::render_facts_json`; nothing else in `core/` or `api/`
uses this (the API's streaming payloads are denormalized, see
`query_service.py::stream_query` and `specs/query-viewer-web-ui/plan.md`'s
"Streaming design")."""

from __future__ import annotations

from mythrix.core.models import (
    ConceptPairCandidates,
    GraphFacts,
    RetrievalContext,
    RetrievedPassage,
    Source,
    Tradition,
)


def _source_payload(source: Source) -> dict:
    return source.model_dump(mode="json", exclude={"id"})


def _tradition_payload(tradition: Tradition) -> dict:
    return tradition.model_dump(mode="json", exclude={"id", "slug"})


def _collect_sources_and_traditions(context: RetrievalContext) -> tuple[dict, dict]:
    """Every `Source`/`Tradition` referenced anywhere in `context`, de-duplicated
    by id — the top-level `sources`/`traditions` lookup tables that
    `--json` output's passages/interpretation reference by id instead of
    embedding in full (many passages typically cite the same handful of
    sources and the same tradition; see `retrieval/pipeline.py`'s
    `_source_and_tradition` docstring)."""
    sources: dict[str, Source] = {}
    traditions: dict[str, Tradition] = {}

    def _note_tradition(tradition: Tradition) -> None:
        traditions[tradition.id] = tradition

    def _note_passage(passage: RetrievedPassage) -> None:
        sources[passage.source.id] = passage.source
        _note_tradition(passage.tradition)

    _note_tradition(context.graph_facts.interpretation.tradition)
    for relationship in context.graph_facts.symbol.relationships:
        _note_tradition(relationship.according_to_tradition)
    for candidates in context.concept_candidates:
        for passage in candidates.passages:
            _note_passage(passage)
    for pair in context.pair_candidates:
        for candidate in pair.candidates:
            _note_passage(candidate.passage)

    return (
        {source_id: _source_payload(source) for source_id, source in sources.items()},
        {tradition_id: _tradition_payload(tradition) for tradition_id, tradition in traditions.items()},
    )


def _interpretation_payload(graph_facts: GraphFacts) -> dict:
    payload = graph_facts.interpretation.model_dump(mode="json", exclude={"tradition"})
    payload["tradition_id"] = graph_facts.interpretation.tradition.id
    return payload


def _graph_facts_payload(graph_facts: GraphFacts) -> dict:
    return {
        "symbol": graph_facts.symbol.model_dump(mode="json"),
        "interpretation": _interpretation_payload(graph_facts),
    }


def _passage_payload(passage: RetrievedPassage) -> dict:
    payload = passage.model_dump(mode="json", exclude={"source", "tradition"})
    payload["source_id"] = passage.source.id
    payload["tradition_id"] = passage.tradition.id
    return payload


def _passages_payload(passages: tuple[RetrievedPassage, ...]) -> list[dict]:
    return [_passage_payload(passage) for passage in passages]


def _pair_candidates_payload(pairs: tuple[ConceptPairCandidates, ...]) -> list[dict]:
    """A list, not a dict keyed by concept text: unlike `concept_candidates`
    (keyed by a single concept, which is unique per query), two concepts in
    a pair have no natural unique string key, and two different pairs could
    otherwise collide."""
    return [
        {
            "concepts": list(pair.concepts),
            "candidates": [
                {
                    "combined_score": candidate.combined_score,
                    "matches": [
                        {"concept": match.concept, "score": match.score, "exact_value": match.exact_value}
                        for match in candidate.matches
                    ],
                    "passage": _passage_payload(candidate.passage),
                }
                for candidate in pair.candidates
            ],
        }
        for pair in pairs
    ]


def facts_json_payload(context: RetrievalContext) -> dict:
    """The full evidentiary chain (FR16): graph facts, candidate passages
    grouped by concept (FR24), and concept-pair convergences (FR27), matching
    what retrieval actually produced. No synthesized summary or
    generation-model identifier, since none were used (FR29). Every
    `Source`/`Tradition` referenced anywhere in the result is listed once
    under `sources`/`traditions` and referenced elsewhere by id
    (`source_id`/`tradition_id`), rather than embedded in full on every
    passage that cites it."""
    sources, traditions = _collect_sources_and_traditions(context)
    return {
        "sources": sources,
        "traditions": traditions,
        "graph_facts": _graph_facts_payload(context.graph_facts),
        "concept_candidates": {
            candidates.concept: _passages_payload(candidates.passages) for candidates in context.concept_candidates
        },
        "pair_candidates": _pair_candidates_payload(context.pair_candidates),
    }
