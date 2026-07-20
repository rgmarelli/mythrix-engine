"""`--json` output payload shape for `RetrievalContext` (FR16) — shared by
`cli/formatting.py::render_facts_json`; nothing else in `core/` or `api/`
uses this (the API's `/api/query` payload is `FragmentQueryResult`, built by
`query_service.py::query_fragments`, see
`specs/query-viewer-facet-redesign/plan.md`)."""

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
    `--json` output's passages/manifestation reference by id instead of
    embedding in full (many passages typically cite the same handful of
    sources; see `retrieval/pipeline.py`'s `_source_for` docstring).
    Traditions come only from the sign side (a manifestation's own tradition,
    and every intersemiotic interpretant's `according_to`) — a retrieved
    passage carries no tradition of its own (FR7)."""
    sources: dict[str, Source] = {}
    traditions: dict[str, Tradition] = {}

    def _note_tradition(tradition: Tradition) -> None:
        traditions[tradition.id] = tradition

    def _note_passage(passage: RetrievedPassage) -> None:
        sources[passage.source.id] = passage.source

    _note_tradition(context.graph_facts.manifestation.tradition)
    for interpretant in context.graph_facts.sign.intersemiotic_interpretants:
        _note_tradition(interpretant.according_to)
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


def _manifestation_payload(graph_facts: GraphFacts) -> dict:
    payload = graph_facts.manifestation.model_dump(mode="json", exclude={"tradition"})
    payload["tradition_id"] = graph_facts.manifestation.tradition.id
    return payload


def _graph_facts_payload(graph_facts: GraphFacts) -> dict:
    return {
        "sign": graph_facts.sign.model_dump(mode="json"),
        "manifestation": _manifestation_payload(graph_facts),
    }


def _passage_payload(passage: RetrievedPassage) -> dict:
    payload = passage.model_dump(mode="json", exclude={"source"})
    payload["source_id"] = passage.source.id
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
    generation-model identifier, since none were used (FR29). Every `Source`
    a passage cites, and every `Tradition` the sign side references, is
    listed once under `sources`/`traditions` and referenced elsewhere by id
    (`source_id`/`tradition_id`), rather than embedded in full on every
    passage/manifestation that cites it."""
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
