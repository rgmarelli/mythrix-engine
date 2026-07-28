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

An interpretant carrying `query.directive: "filter"` (FR-RT-15) contributes an
additional literal-text-filtered query (`query.as_token`) alongside — never
instead of — its plain query. Every filter token recognized anywhere in the
current `GraphFacts` is collected once and applied to every concept's query,
not just the ones in its own group (`_collect_filter_tokens`, `_fact_queries`).
An interpretant carrying `query.directive: "exact"` (FR-EX-01–03) is never
embedded or ANN-searched at all — it is matched by an exhaustive literal
document scan of its own value only (`collect_exact_tokens`,
`ChromaVectorStore.document_matches`), never cross-joined with other
concepts and never assigned a similarity score, since there is no query
vector behind the match. An interpretant carrying `query.directive: "skip"`
(FR-RT-11) is excluded from retrieval entirely (`_is_skipped`,
`_extract_concepts`).

Retrieval searches the full corpus by default (FR-CO-02). Every match is
hydrated with its `Source` for citation (FR-RT-05).

**Concept-scoped matching.** Every `_Query` sharing a concept's value is
Reciprocal-Rank-Fused only against that concept's own queries — never merged
into a pool shared across concepts — and kept to `match_pool_size` per concept.
See ADR-007 for why cross-query merging is rank-based rather than a comparison
of raw similarity scores.

**Region rollup is the sole aggregation (ADR-013).** `retrieve_regions` is the
one entry point over `_search_deep_pools`: matches clearing the floor are
rolled up over contiguous segments of one source and ranked by a
specificity-weighted convergence score (FR-RK-01–FR-RK-10). Convergence is a
ranking signal, not a separate result group.
"""

from __future__ import annotations

import logging
import math
from typing import Literal, NamedTuple

from mythrix.core.embedding import Embedder
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import (
    Facets,
    GraphFacts,
    Interpretant,
    InterpretantFacet,
    IntersemioticInterpretant,
    Match,
    Region,
    RegionQueryResult,
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
    authored it (e.g. "100"), which is what a `Match` reports as its
    interpretant (FR-RT-15), and `as_token` as it must be searched (e.g.
    "hundred"), since the corpus spells numbers out and the curator authors
    this mapping directly via `query.as_token`.

    `kind` records which directive produced this token — `"filter"` (global,
    cross-joined with every concept, FR-RT-15) or `"exact"` (scoped to its own
    concept only, FR-EX-02/03) — so a hit reached through it can be labeled
    back to the right `Match.kind` without re-deriving the directive."""

    value: str
    as_token: str
    kind: Literal["filter", "exact"]


class _Query(NamedTuple):
    """One retrieval query: the text to embed, and an optional exact filter
    token to combine with it as a literal-text filter.

    `filter_token` carries the whole `_FilterToken` rather than just the
    search text so a hit can be attributed back to the authored value
    (FR-RT-15)."""

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
        match_pool_size: int = 100,
        min_score: float = 0.0,
        region_window_size: int = 3,
        region_min_interpretants: int = 1,
    ) -> None:
        self._graph_store = graph_store
        self._vector_store = vector_store
        self._embedder = embedder
        self._match_pool_size = match_pool_size
        self._min_score = min_score
        self._region_window_size = region_window_size
        self._region_min_interpretants = region_min_interpretants

    def _search_deep_pools(
        self, graph_facts: GraphFacts
    ) -> tuple[dict[str, dict[str, VectorHit]], dict[str, set[str]], dict[str, VectorHit], dict[str, str]]:
        """Runs every query from `build_query_texts`, Reciprocal-Rank-Fusing
        hits *within* each concept's own queries only (never across
        concepts), to `match_pool_size` depth, then separately runs an
        exhaustive document scan for every `collect_exact_tokens` token (no
        embedding, no ANN, no `top_k` cap — FR-EX-01/02). Returns
        `(deep_hits_by_concept, filter_token_chunk_ids, all_hits_by_chunk_id,
        token_kind_by_value)` — `token_kind_by_value` maps each token's
        authored `value` to the directive that produced it (`"filter"` or
        `"exact"`, FR-EX-04/05), so callers can label a token-matched hit
        correctly without re-deriving the directive.

        `all_hits_by_chunk_id` holds every hit any query or exact-token scan
        returned, before RRF trims each concept's own pool to
        `match_pool_size` — `retrieve_regions` needs this unfiltered map to
        hydrate a token-matched segment that never ranked into any concept's
        own pool.

        Each concept's `dict[chunk_id, VectorHit]` preserves RRF-rank order
        (insertion order). An `"exact"`-directive token never becomes a
        concept here — see `collect_exact_tokens`."""
        self._lookup_cache: dict[str, Source] = {}

        queries = build_query_texts(graph_facts)
        exact_tokens = collect_exact_tokens(graph_facts)
        query_embeddings = self._embedder.embed([query.text for query in queries]) if queries else []

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
        token_kind_by_value = {
            query.filter_token.value: query.filter_token.kind for query in queries if query.filter_token
        }
        for value, chunk_ids in filter_token_chunk_ids.items():
            logger.info(
                "filter_token=%r as_token=%r hits=%d", value, as_token_by_value.get(value, value), len(chunk_ids)
            )

        for token in exact_tokens:
            hits = self._vector_store.document_matches(token.as_token)
            filter_token_chunk_ids.setdefault(token.value, set()).update(hit.chunk_id for hit in hits)
            for hit in hits:
                all_hits_by_chunk_id.setdefault(hit.chunk_id, hit)
            token_kind_by_value[token.value] = "exact"
            logger.info("exact_token=%r as_token=%r hits=%d", token.value, token.as_token, len(hits))

        return deep_hits_by_concept, filter_token_chunk_ids, all_hits_by_chunk_id, token_kind_by_value

    def retrieve_regions(self, graph_facts: GraphFacts) -> RegionQueryResult:
        """Region-centric retrieval (FR-RK-01–FR-RK-10): rolls up
        floor-clearing interpretant matches over contiguous windows of one
        source's segments, ranked by a specificity-weighted score.

        Aggregates `_search_deep_pools`'s output (ADR-013): a
        match is kept only if it clears `min_score` (FR-RT-14), then matches
        are grouped into regions by contiguous ordinal within
        `region_window_size` (FR-RK-02). Within a region, an interpretant that
        matched more than one of its segments keeps only its single best
        match (FR-RK-01, FR-RK-05): summing every per-segment occurrence
        would let a passage repeating one token across many adjacent
        segments inflate its score by repetition alone (ADR-004). Keyed by
        `interpretant` alone, so a `"concept"` match (a real score) wins over
        an `"exact"`/`"filter"` match (fixed strength) if the same authored
        value happens to reach both (e.g. a `"filter"` token that also
        matches on its own literal reading elsewhere) — an
        `"exact"`-directive value itself never has a `"concept"` match to
        compete with, since it is never embedded (FR-EX-01). That single
        best match still anchors to the specific segment it occurred at
        (FR-RK-09). A region is eligible when its count of distinct matching
        interpretants — of any kind, `"concept"` and `"exact"`/`"filter"`
        alike — reaches `region_min_interpretants` (FR-RK-03/05); the default
        of 1 makes an isolated match a valid, rankable region on its own,
        including one reached only by an `"exact"`-directive token with no
        nearby concept match at all — the whole point of `"exact"` is that
        every literal occurrence surfaces, not only the ones that happen to
        sit next to a semantic match."""
        deep_hits_by_concept, filter_token_chunk_ids, hit_by_chunk_id, token_kind_by_value = self._search_deep_pools(
            graph_facts
        )
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
                    Match(
                        interpretant=filter_value,
                        kind=token_kind_by_value.get(filter_value, "filter"),
                        exact_value=True,
                        segment_ordinal=hit.ordinal,
                    )
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
                distinct_interpretants = {match.interpretant for match in region_matches}
                if len(distinct_interpretants) < self._region_min_interpretants:
                    continue

                score = sum(
                    weight_for(match) * (match.score if match.kind == "concept" else _EXACT_MATCH_STRENGTH)
                    for match in region_matches
                )

                representative_hit = hit_by_segment[(source_id, cluster[0])]
                regions.append(
                    Region(
                        region_id=region_id_of(source_id, cluster[0], cluster[-1]),
                        source=self._source_for(representative_hit),
                        locator=_region_locator(tuple(region_segments)),
                        score=score,
                        convergence_count=len(distinct_interpretants),
                        segments=tuple(region_segments),
                        matches=tuple(region_matches),
                    )
                )

        regions.sort(key=lambda region: region.score, reverse=True)
        return RegionQueryResult(facets=_build_region_facets(regions), regions=tuple(regions))

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

    def _source_for(self, hit: VectorHit) -> Source:
        """Caches `KuzuGraphStore` lookups per `retrieve_regions` call — many
        regions typically come from the same handful of sources, and a
        segment's source never varies by which concept or query surfaced it."""
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
    "filter"` or `"exact"` annotation, or `None` for any other interpretant.
    For `"filter"`, the search text (`as_token`) is authored directly by the
    curator (FR-CO-03, FR-RT-15) — there is no code-side value-to-word
    inference here. For `"exact"`, `as_token` defaults to the interpretant's
    own `value` when the curator leaves it blank (FR-EX-02)."""
    if interpretant.query is None:
        return None
    directive = interpretant.query.directive
    if directive == "filter":
        return _FilterToken(value=interpretant.value, as_token=interpretant.query.as_token, kind="filter")
    if directive == "exact":
        as_token = interpretant.query.as_token or interpretant.value
        return _FilterToken(value=interpretant.value, as_token=as_token, kind="exact")
    return None


def _is_skipped(interpretant: Interpretant) -> bool:
    """True for an interpretant carrying a `query.directive == "skip"`
    annotation (FR-RT-11) — excluded from retrieval entirely, unlike a
    `"filter"` or `"exact"` interpretant, either of which still contributes a
    literal-text filter query."""
    return interpretant.query is not None and interpretant.query.directive == "skip"


def _is_filter_directive(interpretant: Interpretant) -> bool:
    """True only for `query.directive == "filter"` — one of the two
    directives whose interpretant is excluded from the unrestricted plain
    concept query text (FR-RT-15; see also `_is_exact_directive`)."""
    return interpretant.query is not None and interpretant.query.directive == "filter"


def _is_exact_directive(interpretant: Interpretant) -> bool:
    """True only for `query.directive == "exact"` — excluded from the
    unrestricted plain concept query text like `"filter"` (FR-EX-01), but for
    a different reason: an `"exact"` interpretant is never embedded or
    ANN-searched at all, only matched by an exhaustive literal document scan
    of its own value (`collect_exact_tokens`, FR-EX-02) — a membership
    guarantee, not a similarity judgment, so it carries no score."""
    return interpretant.query is not None and interpretant.query.directive == "exact"


def _extract_concepts(interpretants: tuple[Interpretant, ...]) -> list[str]:
    """Every interpretant's value, decomposed to one atomic concept per value
    (`_atomic_values`), for the unrestricted plain query. An interpretant
    carrying `query.directive: "filter"` is excluded here since it's handled
    separately as a global filter (`_collect_filter_tokens`); one carrying
    `"skip"` (FR-RT-11) is excluded outright. An interpretant carrying
    `"exact"` is also excluded — it is never embedded or ANN-searched at all,
    only scanned for directly by `collect_exact_tokens` (FR-EX-01),
    guaranteeing every hit under its value is a genuine literal match rather
    than an unfiltered semantic guess. `properties` are never passed to this
    function — only
    `Manifestation.interpretants` and
    `IntersemioticInterpretant.target_interpretants` ever reach it."""
    concepts: list[str] = []
    for interpretant in interpretants:
        if _is_skipped(interpretant) or _is_filter_directive(interpretant) or _is_exact_directive(interpretant):
            continue
        concepts.extend(_atomic_values(interpretant.value))
    return concepts


def _collect_filter_tokens(interpretant_groups: list[tuple[Interpretant, ...]]) -> list[_FilterToken]:
    """Every recognized `"filter"`-directive token found anywhere across
    `interpretant_groups` — the manifestation's own interpretants, and every
    intersemiotic interpretant's `target_interpretants` — converted to a
    `_FilterToken` and deduplicated by `as_token`, order-preserved by first
    appearance. Collected globally rather than per-group, since the filter
    these become (`_fact_queries`) applies to every concept, not just the
    ones that happen to share a group with the token. The authored form is
    kept alongside the search form so a match can be reported under the value
    the curator wrote (FR-RT-15). `"exact"`-directive tokens are excluded here
    — they never pair with an embedding query at all and are collected instead
    by `collect_exact_tokens` (FR-EX-01/03)."""
    tokens: list[_FilterToken] = []
    seen_as_tokens: set[str] = set()
    for interpretants in interpretant_groups:
        for interpretant in interpretants:
            token = _filter_token_for(interpretant)
            if token and token.kind == "filter" and token.as_token not in seen_as_tokens:
                seen_as_tokens.add(token.as_token)
                tokens.append(token)
    return tokens


def _collect_exact_tokens(interpretant_groups: list[tuple[Interpretant, ...]]) -> list[_FilterToken]:
    """Every recognized `"exact"`-directive token found anywhere across
    `interpretant_groups`, deduplicated by `as_token`. Unlike a `"filter"`
    token, an `"exact"` token never pairs with an embedding query
    (`_fact_queries`) at all — `_search_deep_pools` scans for it directly via
    `ChromaVectorStore.document_matches` (FR-EX-01/02), so which group it
    came from doesn't matter; this collects globally purely so a token
    reachable through two paths (e.g. a bare interpretant and an
    intersemiotic target) isn't scanned for twice."""
    tokens: list[_FilterToken] = []
    seen_as_tokens: set[str] = set()
    for interpretants in interpretant_groups:
        for interpretant in interpretants:
            token = _filter_token_for(interpretant)
            if token and token.kind == "exact" and token.as_token not in seen_as_tokens:
                seen_as_tokens.add(token.as_token)
                tokens.append(token)
    return tokens


def _fact_queries(interpretants: tuple[Interpretant, ...], filter_tokens: list[_FilterToken]) -> list[_Query]:
    """This group's atomic concepts (`_extract_concepts`), each as a plain
    query, plus — for every `"filter"`-directive token recognized anywhere in
    the current `GraphFacts` — one additional filtered variant per concept,
    combined with that token as a literal-text filter (FR-CO-03: alongside,
    never instead of, the plain query). An `"exact"`-directive interpretant
    in this group contributes nothing here at all — it is handled entirely
    by `collect_exact_tokens`/`_search_deep_pools`, never embedded. A group
    with no concepts of its own contributes no plain or `"filter"`-paired
    queries here — a lone `"filter"` token with nothing to filter is handled
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


def _interpretant_groups(graph_facts: GraphFacts) -> list[tuple[Interpretant, ...]]:
    """Every group of interpretants reachable from `graph_facts`: the queried
    sign's own manifestation, then each intersemiotic interpretant's
    `target_interpretants` — the traversal `build_query_texts`,
    `collect_exact_tokens`, and `_filter_token_surface_forms` all need before
    doing their own thing with it."""
    sign, manifestation = graph_facts.sign, graph_facts.manifestation
    groups = [manifestation.interpretants]
    groups += [interpretant.target_interpretants for interpretant in sign.intersemiotic_interpretants]
    return groups


def build_query_texts(graph_facts: GraphFacts) -> list[_Query]:
    """One query per individual atomic concept reachable from the queried
    sign (FR-CO-03): one per atomic concept in each interpretant of the
    sign's own manifestation, then for each intersemiotic interpretant
    (FR-DM-03, FR-SD-04), one per atomic concept about the target. Every
    recognized `"filter"` token anywhere in `graph_facts` becomes a filtered
    variant of every concept, not just the ones in its own group. An
    `"exact"`-directive interpretant's value never appears here at all — see
    `collect_exact_tokens`. `_search_deep_pools` embeds and searches every
    one, then merges the results by rank (RRF; ADR-007), not raw score,
    within each concept."""
    sign, manifestation = graph_facts.sign, graph_facts.manifestation
    filter_tokens = _collect_filter_tokens(_interpretant_groups(graph_facts))

    queries = _fact_queries(manifestation.interpretants, filter_tokens)
    for interpretant in sign.intersemiotic_interpretants:
        queries += _intersemiotic_query_texts(interpretant, filter_tokens)

    if not queries:
        # A sign whose only fact is a bare "filter"-directive interpretant has
        # no concept to attach the token to — search each token's search form
        # on its own rather than dropping it. A sign whose only fact is a
        # bare "exact"-directive interpretant legitimately yields `[]` here —
        # `collect_exact_tokens`/`_search_deep_pools` handle it entirely
        # separately, with no embedding involved.
        queries += [_Query(text=token.as_token) for token in filter_tokens]

    return [query for query in queries if query.text]


def collect_exact_tokens(graph_facts: GraphFacts) -> list[_FilterToken]:
    """Every recognized `"exact"`-directive token reachable from
    `graph_facts` (FR-EX-01/02), deduplicated by `as_token`. Kept separate
    from `build_query_texts`'s ANN-embeddable queries — an `"exact"` token is
    never embedded, only scanned for directly via
    `ChromaVectorStore.document_matches` in `_search_deep_pools`."""
    return _collect_exact_tokens(_interpretant_groups(graph_facts))


def _filter_token_surface_forms(graph_facts: GraphFacts) -> dict[str, str]:
    """Maps every recognized token's curator-authored `value` (the form used
    as `Match.interpretant`, e.g. `"100"`) to its searched `as_token` (the
    literal form actually present in the corpus, e.g. `"hundred"`) — for both
    `"filter"` and `"exact"` tokens, since specificity weighting for either
    must use the searched form, not the authored one, which is what
    `document_frequency` actually counts."""
    groups = _interpretant_groups(graph_facts)
    tokens = _collect_filter_tokens(groups) + _collect_exact_tokens(groups)
    return {token.value: token.as_token for token in tokens}


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


def region_id_of(source_id: str, start_ordinal: int, end_ordinal: int) -> str:
    return f"{source_id}::{start_ordinal}-{end_ordinal}"


def parse_region_id(region_id: str) -> tuple[str, int, int]:
    """Inverse of `region_id_of`. `region_id` is never user-typed — it
    always originates from a region this backend itself produced — so a
    parse failure here means the caller passed something stale or
    malformed, not a validation case worth a friendly message: raises
    `ValueError`."""
    source_id, separator, span = region_id.partition("::")
    if not separator:
        raise ValueError(f"malformed region_id {region_id!r}: missing '::'")
    start, dash, end = span.partition("-")
    if not dash or not start or not end:
        raise ValueError(f"malformed region_id {region_id!r}: missing ordinal range")
    try:
        return source_id, int(start), int(end)
    except ValueError as exc:
        raise ValueError(f"malformed region_id {region_id!r}: non-numeric ordinal range") from exc


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
