"""`RetrievalPipeline`: turns deterministic graph facts into grounding document
passages (FR-CO-02, FR-CO-03, FR-RT-05).

Query text is built entirely from retrieved `GraphFacts`, never raw user input
(FR-CO-03), as one query per atomic concept: one per interpretant value on the
manifestation itself, and one per atomic concept in each intersemiotic
interpretant's target's own interpretants (FR-DM-03, FR-SD-04). A
comma-separated value (several concepts sharing one `type`) is split so each
concept is searched on its own (`_atomic_values`). A sign's canonical name, a
manifestation's denotation, and `properties` at any scope are never searched —
see `build_query_texts`.

An interpretant carrying `query.directive: "filter"` (FR-RT-09) contributes an
additional literal-text-filtered query (`query.as_token`) alongside — never
instead of — its plain query. Every filter token recognized anywhere in the
current `GraphFacts` is collected once and applied to every concept's query,
not just the ones in its own group (`_collect_filter_tokens`, `_fact_queries`).
An interpretant carrying `query.directive: "skip"` (FR-RT-11) is excluded from
retrieval entirely (`_is_skipped`, `_extract_concepts`).

Retrieval searches the full corpus by default (FR-CO-02). Each hit is hydrated
into a `RetrievedPassage` carrying its `Source` for citation (FR-RT-05).

**Concept-scoped retrieval (FR-RT-07).** Every `_Query` sharing a concept's
value is Reciprocal-Rank-Fused only against that concept's own queries — never
merged into a pool shared across concepts — and kept to `top_k` per concept.
See ADR-007 for why cross-query merging is rank-based rather than a comparison
of raw similarity scores.

**Concept-pair convergence (FR-RT-08, FR-RT-09).** `RetrievalPipeline.retrieve`
also emits one `ConceptPairCandidates` per co-occurring concept pair, detected
against a pool deeper than the one displayed (`match_pool_size` vs `top_k`),
alongside — never instead of — the per-concept groups. A pair's combined score
is the geometric mean of its two component scores (`_combined_score`; ADR-007
on why geometric rather than arithmetic). An interpretant reached via a
`"filter"` directive contributes membership to a pair but no score.

Scores are comparable only within a pair group, where every candidate is
scored by the same two queries; they are not comparable across groups.
"""

from __future__ import annotations

import itertools
import logging
import math
from collections.abc import Iterator
from typing import NamedTuple

from mythrix.core.embedding import Embedder
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import (
    ConceptCandidates,
    ConceptMatchScore,
    ConceptPairCandidates,
    Facets,
    GraphFacts,
    Interpretant,
    InterpretantFacet,
    IntersemioticInterpretant,
    Match,
    MergedCandidate,
    Region,
    RegionQueryResult,
    RetrievalContext,
    RetrievedPassage,
    Segment,
    Source,
    SourceFacet,
)
from mythrix.core.vector.store import ChromaVectorStore, VectorHit

logger = logging.getLogger(__name__)

# Damping constant for Reciprocal Rank Fusion (Cormack et al., 2009; ADR-007) —
# large enough that a result's contribution depends mostly on how high it
# ranked *within* its own query, not on how many queries surfaced it or how
# that query's raw score distribution compares to another's.
_RRF_K = 60

# An exact-token match (FR-RT-15) is a literal containment guarantee, not a
# similarity judgment — it carries no comparable magnitude of its own, so it
# enters region scoring (FR-RK-05) at a fixed strength rather than a computed
# one. 1.0 matches the ceiling of `_similarity_score`'s `[-1, 1]` range.
_EXACT_MATCH_STRENGTH = 1.0


class _FilterToken(NamedTuple):
    """A recognized exact-value filter in two forms: `value` as the curator
    authored it (e.g. "100"), which is what appears as a pair member
    (FR-RT-09), and `as_token` as it must be searched (e.g. "hundred"), since
    the corpus spells numbers out and the curator authors this mapping
    directly via `query.as_token`."""

    value: str
    as_token: str


class _Query(NamedTuple):
    """One retrieval query: the text to embed, and an optional exact filter
    token to combine with it as a literal-text filter.

    `filter_token` carries the whole `_FilterToken` rather than just the
    search text so a hit can be attributed back to the authored value
    (FR-RT-09)."""

    text: str
    filter_token: _FilterToken | None = None

    @property
    def document_contains(self) -> str | None:
        return self.filter_token.as_token if self.filter_token else None


class RetrievalPipeline:
    def __init__(
        self,
        *,
        graph_store: KuzuGraphStore,
        vector_store: ChromaVectorStore,
        embedder: Embedder,
        top_k: int = 6,
        match_pool_size: int = 100,
        merge_top_k: int = 6,
        min_score: float = 0.0,
        region_window_size: int = 3,
        region_min_interpretants: int = 1,
    ) -> None:
        self._graph_store = graph_store
        self._vector_store = vector_store
        self._embedder = embedder
        self._top_k = top_k
        self._match_pool_size = match_pool_size
        self._merge_top_k = merge_top_k
        self._min_score = min_score
        self._region_window_size = region_window_size
        self._region_min_interpretants = region_min_interpretants

    def retrieve(self, graph_facts: GraphFacts) -> RetrievalContext:
        """Deterministic Kùzu-then-Chroma retrieval (FR-RT-01): `graph_facts`
        must already be the result of `KuzuGraphStore.get_manifestation`. Thin
        consumer of `iter_candidates` — collects every `ConceptCandidates`/
        `ConceptPairCandidates` it yields into one `RetrievalContext`."""
        concept_candidates: list[ConceptCandidates] = []
        pair_candidates: list[ConceptPairCandidates] = []
        for item in self.iter_candidates(graph_facts):
            if isinstance(item, ConceptCandidates):
                concept_candidates.append(item)
            else:
                pair_candidates.append(item)

        return RetrievalContext(
            graph_facts=graph_facts,
            concept_candidates=tuple(concept_candidates),
            pair_candidates=tuple(pair_candidates),
        )

    def iter_candidates(self, graph_facts: GraphFacts) -> Iterator[ConceptCandidates | ConceptPairCandidates]:
        """Yields each concept's `ConceptCandidates`, then every
        `ConceptPairCandidates` group — the incremental form `retrieve()`
        collects in full. Every concept's deep pool (`_search_deep_pools`) is
        searched before the first item is yielded.

        Each concept's fused ranking is searched to `match_pool_size` depth
        but only its top `top_k` is displayed (FR-RT-07) — the extra depth
        exists purely to detect concept-pair convergence (FR-RT-08) below the
        displayed cutoff. A chunk's displayed score is its best
        (lowest-distance) individual match, used for `min_score` filtering.

        Concept pairs (FR-RT-08, FR-RT-09) are built from every concept's full
        deep pool by `_build_pair_candidates`.
        """
        deep_hits_by_concept, filter_token_chunk_ids, _ = self._search_deep_pools(graph_facts)

        for concept, pool in deep_hits_by_concept.items():
            display_hits = list(pool.values())[: self._top_k]
            passages = tuple(self._hydrate(hit) for hit in display_hits if _similarity_score(hit) >= self._min_score)
            if passages:
                yield ConceptCandidates(concept=concept, passages=passages)

        yield from self._build_pair_candidates(deep_hits_by_concept, filter_token_chunk_ids)

    def _search_deep_pools(
        self, graph_facts: GraphFacts
    ) -> tuple[dict[str, dict[str, VectorHit]], dict[str, set[str]], dict[str, VectorHit]]:
        """Runs every query from `build_query_texts`, Reciprocal-Rank-Fusing
        hits *within* each concept's own queries only (never across
        concepts), to `match_pool_size` depth. Returns `(deep_hits_by_concept,
        filter_token_chunk_ids, all_hits_by_chunk_id)`.

        `all_hits_by_chunk_id` holds every hit any query returned, before RRF
        trims each concept's own pool to `match_pool_size` — `retrieve_regions`
        needs this unfiltered map because an exact-token match's chunk can be
        a genuine filter hit (`document_contains` is a hard containment
        guarantee) without ranking highly enough for any single *concept* to
        survive into that concept's own RRF-trimmed pool.

        Each concept's `dict[chunk_id, VectorHit]` preserves RRF-rank order
        (insertion order), so a caller taking its first `top_k` entries gets
        the same displayed slice `iter_candidates`'s `ConceptCandidates`
        would."""
        self._lookup_cache: dict[str, Source] = {}

        queries = build_query_texts(graph_facts)
        query_embeddings = self._embedder.embed([query.text for query in queries])

        queries_by_concept: dict[str, list[tuple[_Query, list[float]]]] = {}
        for query, embedding in zip(queries, query_embeddings, strict=True):
            queries_by_concept.setdefault(query.text, []).append((query, embedding))

        deep_hits_by_concept: dict[str, dict[str, VectorHit]] = {}
        filter_token_chunk_ids: dict[str, set[str]] = {}
        all_hits_by_chunk_id: dict[str, VectorHit] = {}

        for concept, concept_queries in queries_by_concept.items():
            best_hit_by_chunk_id: dict[str, VectorHit] = {}
            rrf_score_by_chunk_id: dict[str, float] = {}
            for query, embedding in concept_queries:
                hits = self._vector_store.similarity_search(
                    embedding, top_k=self._match_pool_size, document_contains=query.document_contains
                )
                if query.filter_token is not None:
                    filter_token_chunk_ids.setdefault(query.filter_token.value, set()).update(
                        hit.chunk_id for hit in hits
                    )
                for rank, hit in enumerate(hits, start=1):
                    existing = best_hit_by_chunk_id.get(hit.chunk_id)
                    if existing is None or hit.distance < existing.distance:
                        best_hit_by_chunk_id[hit.chunk_id] = hit
                        all_hits_by_chunk_id[hit.chunk_id] = hit
                    rrf_score_by_chunk_id[hit.chunk_id] = rrf_score_by_chunk_id.get(hit.chunk_id, 0.0) + 1.0 / (
                        _RRF_K + rank
                    )

            ranked_chunk_ids = sorted(
                rrf_score_by_chunk_id, key=lambda chunk_id: rrf_score_by_chunk_id[chunk_id], reverse=True
            )
            deep_chunk_ids = ranked_chunk_ids[: self._match_pool_size]
            deep_hits_by_concept[concept] = {chunk_id: best_hit_by_chunk_id[chunk_id] for chunk_id in deep_chunk_ids}

            variants = [
                query.text if query.filter_token is None else f"{query.text}+filter:{query.filter_token.as_token}"
                for query, _ in concept_queries
            ]
            hits_above_floor = sum(
                1 for hit in deep_hits_by_concept[concept].values() if _similarity_score(hit) >= self._min_score
            )
            logger.info("concept=%r queries=%s hits_above_floor=%d", concept, variants, hits_above_floor)

        as_token_by_value = {
            query.filter_token.value: query.filter_token.as_token for query in queries if query.filter_token
        }
        for value, chunk_ids in filter_token_chunk_ids.items():
            logger.info(
                "filter_token=%r as_token=%r hits=%d", value, as_token_by_value.get(value, value), len(chunk_ids)
            )

        return deep_hits_by_concept, filter_token_chunk_ids, all_hits_by_chunk_id

    def retrieve_regions(self, graph_facts: GraphFacts) -> RegionQueryResult:
        """Region-centric retrieval (FR-RK-01–FR-RK-10): rolls up
        floor-clearing interpretant matches over contiguous windows of one
        source's segments, ranked by a specificity-weighted score.

        Uses the same underlying search as `iter_candidates`
        (`_search_deep_pools`); only what's aggregated and returned differs: a
        match is kept only if it clears `min_score` (FR-RT-14), then matches
        are grouped into regions by contiguous ordinal within
        `region_window_size` (FR-RK-02). Within a region, an interpretant that
        matched more than one of its segments keeps only its single best
        match (FR-RK-01, FR-RK-05) — summing every per-segment occurrence
        would let a passage repeating one token across many adjacent segments
        inflate its score by repetition alone (ADR-004). That single best
        match still anchors to the specific segment it occurred at
        (FR-RK-09). A region is eligible when its count of distinct *concept*
        interpretants reaches `region_min_interpretants` — an exact-token
        match is excluded from this count since it is a containment
        guarantee, not a semantic signal, and shouldn't alone make a region
        eligible; the default of 1 makes an isolated strong match a valid,
        rankable region on its own (FR-RK-03)."""
        deep_hits_by_concept, filter_token_chunk_ids, hit_by_chunk_id = self._search_deep_pools(graph_facts)
        surface_form_by_token_value = _filter_token_surface_forms(graph_facts)

        matches_by_segment: dict[tuple[str, int], list[Match]] = {}
        hit_by_segment: dict[tuple[str, int], VectorHit] = {}

        for concept, pool in deep_hits_by_concept.items():
            for hit in pool.values():
                score = _similarity_score(hit)
                if score < self._min_score:
                    continue
                key = (hit.source_id, hit.ordinal)
                hit_by_segment.setdefault(key, hit)
                matches_by_segment.setdefault(key, []).append(
                    Match(interpretant=concept, kind="concept", score=score, segment_ordinal=hit.ordinal)
                )

        for filter_value, chunk_ids in filter_token_chunk_ids.items():
            for chunk_id in chunk_ids:
                hit = hit_by_chunk_id.get(chunk_id)
                if hit is None:
                    continue
                key = (hit.source_id, hit.ordinal)
                hit_by_segment.setdefault(key, hit)
                matches_by_segment.setdefault(key, []).append(
                    Match(interpretant=filter_value, kind="exact", exact_value=True, segment_ordinal=hit.ordinal)
                )

        ordinals_by_source: dict[str, set[int]] = {}
        for source_id, ordinal in matches_by_segment:
            ordinals_by_source.setdefault(source_id, set()).add(ordinal)

        weight_cache: dict[str, float] = {}

        def weight_for(match: Match) -> float:
            surface_form = surface_form_by_token_value.get(match.interpretant, match.interpretant)
            if surface_form not in weight_cache:
                weight_cache[surface_form] = self._specificity_weight(surface_form)
            return weight_cache[surface_form]

        regions: list[Region] = []
        for source_id, ordinals in ordinals_by_source.items():
            for cluster in _cluster_ordinals(ordinals, self._region_window_size):
                region_segments: list[Segment] = []
                best_match_by_interpretant: dict[str, Match] = {}
                for ordinal in cluster:
                    key = (source_id, ordinal)
                    hit = hit_by_segment[key]
                    region_segments.append(
                        Segment(ordinal=ordinal, locator=hit.locator, text=hit.text, section=hit.section)
                    )
                    for match in matches_by_segment[key]:
                        existing = best_match_by_interpretant.get(match.interpretant)
                        if existing is None or match.score > existing.score:
                            best_match_by_interpretant[match.interpretant] = match

                region_matches = list(best_match_by_interpretant.values())
                concept_interpretants = {match.interpretant for match in region_matches if match.kind == "concept"}
                if len(concept_interpretants) < self._region_min_interpretants:
                    continue

                score = sum(
                    weight_for(match) * (match.score if match.kind == "concept" else _EXACT_MATCH_STRENGTH)
                    for match in region_matches
                )

                representative_hit = hit_by_segment[(source_id, cluster[0])]
                regions.append(
                    Region(
                        region_id=f"{source_id}::{cluster[0]}-{cluster[-1]}",
                        source=self._source_for(representative_hit),
                        locator=_region_locator(tuple(region_segments)),
                        score=score,
                        convergence_count=len(concept_interpretants),
                        segments=tuple(region_segments),
                        matches=tuple(region_matches),
                    )
                )

        regions.sort(key=lambda region: region.score, reverse=True)
        return RegionQueryResult(facets=_build_region_facets(regions), regions=tuple(regions))

    def _build_pair_candidates(
        self,
        deep_hits_by_concept: dict[str, dict[str, VectorHit]],
        filter_token_chunk_ids: dict[str, set[str]],
    ) -> tuple[ConceptPairCandidates, ...]:
        """One `ConceptPairCandidates` per co-occurring pair (FR-RT-08): every
        unordered pair of semantic concepts sharing a chunk in their deep
        pools, plus every semantic concept paired with every recognized
        exact-value filter token it shares a chunk with (FR-RT-09). A pair of
        two filter tokens is never emitted — a filter token carries no score
        of its own, so there is nothing to rank such a pair by. Groups are
        sorted strongest-first by their own top candidate; this ordering is a
        display heuristic, not a claim that one group's score is
        commensurable with another's."""
        concepts = sorted(deep_hits_by_concept)
        groups: list[ConceptPairCandidates] = []

        for concept_a, concept_b in itertools.combinations(concepts, 2):
            pool_a, pool_b = deep_hits_by_concept[concept_a], deep_hits_by_concept[concept_b]
            candidates = []
            for chunk_id in set(pool_a) & set(pool_b):
                score_a, score_b = _similarity_score(pool_a[chunk_id]), _similarity_score(pool_b[chunk_id])
                combined = _combined_score((score_a, score_b))
                if combined < self._min_score:
                    continue
                candidates.append(
                    MergedCandidate(
                        passage=self._hydrate(pool_a[chunk_id]),
                        matches=(
                            ConceptMatchScore(concept=concept_a, score=score_a),
                            ConceptMatchScore(concept=concept_b, score=score_b),
                        ),
                        combined_score=combined,
                    )
                )
            self._append_group(groups, (concept_a, concept_b), candidates)

        for concept, filter_value in itertools.product(concepts, sorted(filter_token_chunk_ids)):
            pool = deep_hits_by_concept[concept]
            candidates = []
            for chunk_id in set(pool) & filter_token_chunk_ids[filter_value]:
                score = _similarity_score(pool[chunk_id])
                if score < self._min_score:
                    continue
                candidates.append(
                    MergedCandidate(
                        passage=self._hydrate(pool[chunk_id]),
                        matches=(
                            ConceptMatchScore(concept=concept, score=score),
                            ConceptMatchScore(concept=filter_value, score=0.0, exact_value=True),
                        ),
                        combined_score=score,
                    )
                )
            self._append_group(groups, (concept, filter_value), candidates)

        groups.sort(key=lambda group: group.candidates[0].combined_score, reverse=True)
        return tuple(groups)

    def _append_group(
        self, groups: list[ConceptPairCandidates], concepts: tuple[str, str], candidates: list[MergedCandidate]
    ) -> None:
        if not candidates:
            return
        candidates.sort(key=lambda candidate: candidate.combined_score, reverse=True)
        groups.append(ConceptPairCandidates(concepts=concepts, candidates=tuple(candidates[: self._merge_top_k])))

    def _specificity_weight(self, surface_form: str) -> float:
        """A rarer literal surface form yields a strictly higher weight
        (FR-RK-04/FR-RK-06): `log(N / df(surface_form))`, `N` the total number
        of ingested segments and `df` the count of segments literally
        containing `surface_form` on whole-word boundaries
        (`ChromaVectorStore.document_frequency`, never a count derived from
        dense embedding scores — ADR-004 found that diffuse and misleading).
        `df` is floored at 1 so this never divides by zero or takes
        `log(0)`."""
        corpus_size = self._vector_store.count()
        if corpus_size <= 0:
            return 0.0
        df = max(self._vector_store.document_frequency(surface_form), 1)
        return math.log(corpus_size / df)

    def _hydrate(self, hit: VectorHit) -> RetrievedPassage:
        return RetrievedPassage(
            chunk_id=hit.chunk_id,
            source=self._source_for(hit),
            text=hit.text,
            locator=hit.locator,
            score=_similarity_score(hit),
            chunk_index=hit.chunk_index,
            char_start=hit.char_start,
            char_end=hit.char_end,
            embedding_model=hit.embedding_model,
        )

    def _source_for(self, hit: VectorHit) -> Source:
        """Caches `KuzuGraphStore` lookups per `retrieve()` call — the same
        chunk can be hydrated once for its own concept's display list and
        again while building a pair candidate, and a passage's source never
        varies by which concept or query surfaced it."""
        cached = self._lookup_cache.get(hit.source_id)
        if cached is None:
            cached = self._graph_store.get_source(hit.source_id)
            self._lookup_cache[hit.source_id] = cached
        return cached


def _atomic_values(value: str) -> list[str]:
    """A comma-separated value (several distinct concepts sharing one
    curator-chosen `type`) is split so each concept is searched entirely on
    its own. A value with no comma is already atomic and comes back as a
    one-item list."""
    return [part.strip() for part in value.split(",") if part.strip()]


def _filter_token_for(interpretant: Interpretant) -> _FilterToken | None:
    """The `_FilterToken` for an interpretant carrying a `query.directive ==
    "filter"` annotation, or `None` for any other interpretant. The search
    text (`as_token`) is authored directly by the curator (FR-CO-03,
    FR-RT-09) — there is no code-side value-to-word inference here."""
    if interpretant.query is not None and interpretant.query.directive == "filter":
        return _FilterToken(value=interpretant.value, as_token=interpretant.query.as_token)
    return None


def _is_skipped(interpretant: Interpretant) -> bool:
    """True for an interpretant carrying a `query.directive == "skip"`
    annotation (FR-RT-11) — excluded from retrieval entirely, unlike a
    `"filter"` interpretant, which still contributes a literal-text filter
    query."""
    return interpretant.query is not None and interpretant.query.directive == "skip"


def _extract_concepts(interpretants: tuple[Interpretant, ...]) -> list[str]:
    """Every interpretant's value, decomposed to one atomic concept per value
    (`_atomic_values`). An interpretant carrying `query.directive: "filter"`
    is excluded here since it's handled separately as a global filter
    (`_collect_filter_tokens`); one carrying `"skip"` (FR-RT-11) is excluded
    outright. `properties` are never passed to this function — only
    `Manifestation.interpretants` and
    `IntersemioticInterpretant.target_interpretants` ever reach it."""
    concepts: list[str] = []
    for interpretant in interpretants:
        if _is_skipped(interpretant) or _filter_token_for(interpretant) is not None:
            continue
        concepts.extend(_atomic_values(interpretant.value))
    return concepts


def _collect_filter_tokens(interpretant_groups: list[tuple[Interpretant, ...]]) -> list[_FilterToken]:
    """Every recognized exact-value filter token found anywhere across
    `interpretant_groups` — the manifestation's own interpretants, and every
    intersemiotic interpretant's `target_interpretants` — converted to a
    `_FilterToken` and deduplicated by `as_token`, order-preserved by first
    appearance. Collected globally rather than per-group, since the filter
    these become (`_fact_queries`) applies to every concept, not just the
    ones that happen to share a group with the token. The authored form is
    kept alongside the search form so it can surface as a pair member in its
    own right (FR-RT-09)."""
    tokens: list[_FilterToken] = []
    seen_as_tokens: set[str] = set()
    for interpretants in interpretant_groups:
        for interpretant in interpretants:
            token = _filter_token_for(interpretant)
            if token and token.as_token not in seen_as_tokens:
                seen_as_tokens.add(token.as_token)
                tokens.append(token)
    return tokens


def _fact_queries(interpretants: tuple[Interpretant, ...], filter_tokens: list[_FilterToken]) -> list[_Query]:
    """This group's atomic concepts (`_extract_concepts`), each as a plain
    query, plus — for every filter token recognized anywhere in the current
    `GraphFacts` — one additional filtered variant per concept, combined with
    that token as a literal-text filter (FR-CO-03: alongside, never instead
    of, the plain query). A group with no concepts of its own contributes no
    queries here — a lone filter token with nothing to filter is handled
    once, globally, by `build_query_texts`."""
    concepts = _extract_concepts(interpretants)
    queries = [_Query(text=concept) for concept in concepts]
    for token in filter_tokens:
        queries += [_Query(text=concept, filter_token=token) for concept in concepts]
    return queries


def _intersemiotic_query_texts(
    interpretant: IntersemioticInterpretant, filter_tokens: list[_FilterToken]
) -> list[_Query]:
    """One query per individual atomic concept about an intersemiotic
    interpretant's target — its own manifestation-level interpretants across
    every tradition it is manifested under (`target_interpretants`). Already
    hydrated by `KuzuGraphStore._get_sign_intersemiotic_interpretants`, so
    this needs no extra graph fetch here. Never includes the target's
    `properties` (FR-CO-03, FR-DM-04), or the target's own bare name as a
    query in its own right (ADR-007)."""
    return _fact_queries(interpretant.target_interpretants, filter_tokens)


def build_query_texts(graph_facts: GraphFacts) -> list[_Query]:
    """One query per individual atomic concept reachable from the queried
    sign (FR-CO-03): one per atomic concept in each interpretant of the
    sign's own manifestation, then for each intersemiotic interpretant
    (FR-DM-03, FR-SD-04), one per atomic concept about the target. Every
    recognized filter token anywhere in `graph_facts` becomes a filtered
    variant of every concept, not just the ones in its own group.
    `RetrievalPipeline.retrieve` embeds and searches every one, then merges
    the results by rank (RRF; ADR-007), not raw score, within each concept."""
    sign, manifestation = graph_facts.sign, graph_facts.manifestation
    interpretant_groups = [manifestation.interpretants]
    interpretant_groups += [interpretant.target_interpretants for interpretant in sign.intersemiotic_interpretants]
    filter_tokens = _collect_filter_tokens(interpretant_groups)

    queries = _fact_queries(manifestation.interpretants, filter_tokens)
    for interpretant in sign.intersemiotic_interpretants:
        queries += _intersemiotic_query_texts(interpretant, filter_tokens)

    if not queries:
        # A sign whose only fact is a bare exact-value interpretant has no
        # concept to attach a filter token to — search each token's search
        # form on its own rather than dropping it. Not tagged with
        # `filter_token=`: with no concept to pair against, it can't
        # participate in FR-RT-08/FR-RT-09 convergence anyway.
        queries += [_Query(text=token.as_token) for token in filter_tokens]

    return [query for query in queries if query.text]


def _filter_token_surface_forms(graph_facts: GraphFacts) -> dict[str, str]:
    """Maps every recognized filter token's curator-authored `value` (the
    form used as `Match.interpretant`, e.g. `"100"`) to its searched
    `as_token` (the literal form actually present in the corpus, e.g.
    `"hundred"`) — specificity weighting for a token interpretant must use
    the searched form, not the authored one, since that's what
    `document_frequency` actually counts."""
    sign, manifestation = graph_facts.sign, graph_facts.manifestation
    interpretant_groups = [manifestation.interpretants]
    interpretant_groups += [interpretant.target_interpretants for interpretant in sign.intersemiotic_interpretants]
    return {token.value: token.as_token for token in _collect_filter_tokens(interpretant_groups)}


def _cluster_ordinals(ordinals: set[int], window_size: int) -> list[list[int]]:
    """Chains eligible ordinals (already known to be from the same source)
    into contiguous regions: sorted ascending, an ordinal joins the region in
    progress when it is within `window_size` of that region's most recent
    ordinal, else it starts a new region (FR-RK-02) — so a region can span
    more than `window_size` end-to-end when matches occur in a close-packed
    chain."""
    ordered = sorted(ordinals)
    clusters: list[list[int]] = []
    for ordinal in ordered:
        if clusters and ordinal - clusters[-1][-1] <= window_size:
            clusters[-1].append(ordinal)
        else:
            clusters.append([ordinal])
    return clusters


def _region_locator(segments: tuple[Segment, ...]) -> str:
    """A single-segment region reuses that segment's own locator. A
    multi-segment region merges the first and last locator's trailing part
    when they share a common prefix (`"Genesis 21:5"` + `"Genesis 21:6"` ->
    `"Genesis 21:5–6"`); otherwise the two full locators are joined, still
    unambiguous."""
    if len(segments) == 1:
        return segments[0].locator
    first, last = segments[0].locator, segments[-1].locator
    prefix = first.rpartition(":")[0]
    if prefix and last.startswith(prefix + ":"):
        return f"{first}–{last[len(prefix) + 1 :]}"
    return f"{first}–{last}"


def _build_region_facets(regions: list[Region]) -> Facets:
    """One `SourceFacet` per distinct source and one `InterpretantFacet` per
    distinct interpretant, counted across the already-eligible region list —
    the region-centric counterpart to `_build_facets`."""
    source_counts: dict[str, SourceFacet] = {}
    for region in regions:
        existing = source_counts.get(region.source.id)
        label = region.source.title
        if existing is None:
            source_counts[region.source.id] = SourceFacet(id=region.source.id, label=label, count=1)
        else:
            source_counts[region.source.id] = existing.model_copy(update={"count": existing.count + 1})

    interpretant_counts: dict[str, int] = {}
    for region in regions:
        for match in region.matches:
            interpretant_counts[match.interpretant] = interpretant_counts.get(match.interpretant, 0) + 1

    return Facets(
        sources=tuple(source_counts.values()),
        interpretants=tuple(
            InterpretantFacet(value=value, count=count) for value, count in interpretant_counts.items()
        ),
    )


def _similarity_score(hit: VectorHit) -> float:
    """`ChromaVectorStore` is configured for cosine distance (`[0, 2]`, 0 =
    identical) — `1 - distance` gives a similarity score where higher is
    better, matching `Settings.retrieval_min_score`'s "keep at or above this"
    semantics."""
    return 1.0 - hit.distance


def _combined_score(scores: tuple[float, ...]) -> float:
    """Geometric mean of a concept pair's semantic component scores, clamped
    at zero per component before multiplying (FR-RT-08). `_similarity_score`
    is `1 - cosine_distance`, which spans `[-1, 1]`, not `[0, 1]` — a negative
    component would otherwise make the root complex.

    Geometric rather than arithmetic because convergence is conjunctive, not
    additive — see ADR-007 for why only the geometric mean distinguishes a
    lopsided single-concept match from a genuine intersection."""
    clamped = tuple(max(0.0, score) for score in scores)
    return math.prod(clamped) ** (1.0 / len(clamped))
