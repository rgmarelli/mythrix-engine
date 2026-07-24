"""`RetrievalPipeline`: turns deterministic graph facts into grounding document
passages (plan.md "Retrieval pipeline", FR-CO-02/FR-CO-03/FR-RT-05).

Similarity-search query text is built entirely from already-retrieved
`GraphFacts` (interpretant values) — never from raw user input (FR-CO-03) — as *many*
separate queries, one per individual atomic concept, never grouped into a
combined string: one query per atomic concept in each of the manifestation's own
`interpretants`, and for every `intersemiotic_interpretants` entry (FR-DM-03, FR-SD-04),
one per atomic concept about the target's own `target_interpretants`. A value that
lists several distinct concepts separated by commas (e.g. a Hebrew letter's
`meaning`, "Monkey, eye of the needle") is split further still, one query per
concept — those aren't one idea, they're several sharing a `type`, and one ("eye
of the needle" — an impossible-thing-made-possible image, echoing a child born to
hundred-year-old parents) can be exactly the useful part while another ("Monkey")
contributes nothing. No `type:` label is included (see the TODO below on why
that's deliberately unresolved rather than reasoned out), and there's no combined
descriptive-identity query either: a sign's canonical name, a manifestation's
display name/denotation, and any `properties` (at either scope) are never
searched at all, only a manifestation's individual interpretant values — so every
sign is represented by comparably short, atomic queries rather than some being
diluted by a long paragraph others don't have, and properties (structural,
non-interpretive facts) never inject a stray token into a similarity search
regardless of whether they belong to the queried sign or to an
intersemiotic-interpretant target.

An interpretant carrying a `query.directive: "filter"` annotation (FR-RT-09) is a
special case, handled differently from every other concept: semantic similarity
can't distinguish "this passage happens to mention some number" from "this
passage mentions exactly this number" — a real case found `numeric_value: "100"`
(bare, embedded as text) surfacing a passage about measuring units ("the ephi and
the bate") with no thematic connection to anything, purely because it also
contains numbers. So a curator authors the filter's search text directly
(`query.as_token`, e.g. "hundred" for a Hebrew letter's gematria value `"100"`)
and it is used as a literal-text filter (`document_contains`,
`ChromaVectorStore.similarity_search`) — but as a *second, additional* query
alongside each plain concept query, not a replacement for it. An earlier version
made the filtered version replace the plain one, which silently returns zero
results for any card where no single passage happens to combine the exact value
and the concept — for most signs, most of the time, since that's a fairly
specific coincidence. Killing real candidates that way is worse than an
occasional missed boost, so now every concept is always searched plainly too; the
filtered variant is purely additive, a second independent ranking that rewards
(via Reciprocal Rank Fusion) a passage combining both signals without excluding
one that only matches the concept. See `_fact_queries`. Because that filter is a
*hard* Chroma `where_document` constraint, every hit it returns provably contains
the token — which is what lets it appear as a first-class member of a concept
pair (FR-RT-09, see "Concept-pair convergence" below).

An interpretant carrying `query.directive: "skip"` (FR-RT-11) is the simpler,
harder case: no query, plain or filtered, is ever built for it — it takes no
part in retrieval at all, present only as an ordinary fact elsewhere in the
Sign Graph. Distinct from `"filter"`: a filter interpretant becomes an
additional literal-text query, contributing membership without a score; a
skip interpretant contributes nothing to retrieval whatsoever. For a
correspondence-sourced meaning with no reliable literal form in the corpus and
too diffuse a semantic signal to be worth searching on its own (unlike a
gematria value, which has both), skip removes it cleanly instead of leaving it
to compete as a noisy, low-value concept. See `_extract_concepts`.

A real query (The Sun, corresponding to the Hebrew letter Qoph) drove every
round of this design, in order: embedding "laughter" (Qoph's Sepher Yetzirah
foundation) completely alone ranked the one Bible passage it should surface at
#4 of ~1600 chunks; grouped with Qoph's *other* facts (one query per
relationship, not yet per fact) it only reached #57; labelled with its own type
("foundation: laughter" instead of bare "laughter") it dropped to #30;
averaged into one ~30-word query combining everything the card and the letter
both carry, it dropped past #100. Isolating every concept this far (see
`build_query_texts`) got "laughter" back to #4 *within its own search* — but
it still didn't survive the final merge, because that merge compared raw
cosine scores across differently-distributed queries: "hebrew_letter Qoph" (a
bare proper name) scored *higher* across the board than "laughter" purely
because "Qoph" sits closer to generic ceremonial/priestly vocabulary in the
embedding space, nothing to do with relevance. Reciprocal Rank Fusion
(`RetrievalPipeline.retrieve`) and disabling the bare target-name query
(`_relationship_query_texts`) fixed that. The exact-value filter above is the
newest fix, for a different failure mode found afterward: `numeric_value: "100"`
surfacing thematically unrelated passages that merely contained other numbers.

TODO(retrieval-semantics): dropping the `type:` label measurably helped in some
cases above and hurt in others — there was no clean universal rule, just a
per-fact empirical trade-off, and the label was cut anyway because "search the
bare value" was the simpler, more predictable default to start from. Revisit
whether some lighter-weight semantic signal could recover the cases a bare
label would have helped, without reintroducing the cases it hurt — worth
checking specifically against the Hebrew letter data (`meaning` vs
`foundation` vs `constellation`/`planet` currently look identical to
retrieval once the label's gone, despite being conceptually distinct kinds of
fact).

TODO(retrieval-semantics): an intersemiotic interpretant's target sign's bare
name (e.g. "Qoph") is disabled as its own query for now, for every relationship
regardless of domain — not special-cased to Hebrew letters specifically, since
the same failure mode (a bare proper noun scoring high for generic reasons
unrelated to meaning) will recur for any symbol system's names, not just this
one. But the name genuinely is a useful, specific search target in the right
corpus — e.g. Psalm 119's stanzas are each headed by a Hebrew letter name, and a
corpus that was itself Kabbalistic (the Sepher Yetzirah, the Bahir) would
discuss these names constantly and meaningfully. Revisit as a corpus-aware or
per-relationship-type decision, not a blanket on/off switch, once there's a
concrete case that needs it.

Retrieval searches the full document corpus by default (FR-CO-02) — every ingested
document is an independent corpus document (e.g. a scriptural text) meant to
be read *through* the graph's established symbolism, with no interpretive
tradition of its own to scope by; see plan.md's Risks for what this
deliberately does not yet solve (blending competing *interpretive* traditions,
should a second interpretive tradition's own commentary ever be ingested).
Each hit is hydrated into a `RetrievedPassage` carrying the full verbatim
chunk text plus its `Source` (whose `citation_label` attributes it), so the
CLI can render a References section without re-reading the original document
file (FR-RT-05).

**Concept-scoped retrieval (FR-RT-07).** Results are grouped by concept — every
`_Query` derived from the same atomic value (its plain form plus, if present,
its exact-value-filtered variant; see `_fact_queries`) shares that value as
its `text`, which doubles as the concept's grouping key. Each concept's hits
are Reciprocal-Rank-Fused *only against that concept's own queries* and kept
up to `top_k` **per concept**, never merged into one shared pool across
concepts. This is a deliberate fix, not a tuning tweak: a card with a precise
exact-value fact can generate many more queries than one without (see the module
docstring above), and merging everything into one shared final cutoff let a
handful of low-signal concepts (e.g. `naked child`, `white horse`) crowd out
a high-signal one (`laughter`, ranked #1 within its own query) purely by
outnumbering it — confirmed against the real `~/.mythrix` store for The Sun.
Concept-scoping means every concept gets its own retrieval budget instead of
competing for a shared one.

**Exact-value filters apply globally, not just within the group they came
from (`build_query_texts`).** A recognized filter token (e.g. Qoph's gematria,
`query.as_token == "hundred"`) is not limited to filtering concepts in its own
group — Qoph's own `meaning`/`foundation`/`constellation` concepts get the
"hundred" filter, and so does The Sun's own keywords (`naked`, `child`, ...),
even though those come from a completely different part of the graph. A real
passage can combine a concept from one part of the graph with a filter token
from another (Genesis 21: a *child* born when his father was *a hundred* years
old). Confirmed empirically before this design was settled: querying `child` +
the `hundred` filter (combining a keyword that had never gotten this filter with
a value from an unrelated relationship) ranked the Genesis 21 passage at #3 and
the Genesis 17 passage (a second, independent laughter-at-a-hundred-years-old
account, "Abraham fell upon his face, and laughed... shall a son be born to him
that is a hundred years old?") at #25 — the best combined ranking for *both*
passages found across every query shape tried, better than any single concept
alone. So every recognized filter token anywhere in a query's `GraphFacts` (the
manifestation's own interpretants, and every intersemiotic-interpretant target's
`target_interpretants`) is collected once (`_collect_filter_tokens`) and applied
as an additional filtered variant to *every* concept's plain query, regardless of
which group originated the token — still additive, never replacing the plain
query, per the boost-not-hard-filter principle above.

**Concept-pair convergence (FR-RT-08, FR-RT-09).** Per-concept grouping above discards
the single most useful thing retrieval knows: when two independently-derived
concepts retrieve the *same* passage, that convergence is itself the finding.
Under concept-scoping alone, Genesis 21:5 — a child born to a hundred-year-old
father, named "laughter" — is merely an ordinary member of the `child` list and
of the `laughter` list, with nothing recording that it was one passage all
along. `RetrievalPipeline.retrieve` therefore also emits one
`ConceptPairCandidates` per co-occurring concept pair, *alongside* (never
instead of) the per-concept groups. Because the groups are additive, a strong
single-concept match cannot lose to a convergent one — it still stands in its
own group — so no ranking rule has to adjudicate between the two.

Two details carry the design. First, pairs are detected against a pool deeper
than the one displayed (`match_pool_size` vs `top_k`): intersecting only the
displayed candidates would miss a passage ranked #1 for one concept and #9 for
another, which is exactly the lopsided-but-real convergence worth surfacing.
Second, a pair's combined score is the *geometric* mean of its semantic
components, clamped at zero (`_combined_score`) — convergence is conjunctive,
not additive, and only a geometric mean distinguishes a passage scoring
(0.57, 0.53) from one scoring (0.90, 0.20), which share both a sum and a mean
despite only the first genuinely sitting at the intersection. That distinction
is *created* by the deep pool: at display depth alone, anything appearing in
two lists was decent at both, so lopsided pairs were rare and the formula
wouldn't have mattered. An interpretant carrying `query.directive == "filter"`
contributes membership but no score (FR-RT-09) — it arrives via a hard text filter,
so its match is a guarantee rather than a magnitude, and scoring it as 1.0 would
let every filter-bearing pair dominate the output.

Scores are comparable only *within* a pair group, where every candidate is
scored by the same two queries so any per-query bias is constant across the
rows being compared. They are not comparable across groups — see plan.md's
Risks, and this module's own history above on why raw cross-query score
comparison was abandoned for RRF in the first place.
"""

from __future__ import annotations

import itertools
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

# Damping constant for Reciprocal Rank Fusion (Cormack et al., 2009) — large
# enough that a result's contribution depends mostly on how high it ranked
# *within* its own query, not on how many queries happened to surface it or
# how that query's raw score distribution compares to another's.
_RRF_K = 60

# An exact-token match (FR-RT-15) is a literal containment guarantee, not a
# similarity judgment — it carries no comparable magnitude of its own, so it
# enters region scoring (FR-RK-05) at a fixed strength rather than a computed one.
# 1.0 matches the ceiling of `_similarity_score`'s `[-1, 1]` range: a
# guaranteed containment is treated as at least as strong as a perfect
# semantic match.
_EXACT_MATCH_STRENGTH = 1.0


class _FilterToken(NamedTuple):
    """A recognized exact-value filter in two forms: `value` as the curator
    authored it ("100"), which is what a researcher recognizes and what appears
    as a pair member (FR-RT-09), and `as_token` as it must be searched ("hundred"),
    since the corpus spells numbers out and the curator authors this mapping
    directly via `query.as_token` rather than the code inferring it. Kept
    together because the search form alone is not presentable and the authored
    form alone is not searchable."""

    value: str
    as_token: str


class _Query(NamedTuple):
    """One retrieval query: the text to embed, and an optional exact filter
    token to combine with it as a literal-text filter — see this module's
    docstring on when a query gets one.

    `filter_token` carries the whole `_FilterToken` rather than just the search
    text so a hit can be attributed back to the authored value (FR-RT-09). Every hit
    from a query bearing one provably contains that token: `document_contains`
    is a hard `where_document` constraint, not a boost."""

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
        """Deterministic Kùzu-then-Chroma retrieval (FR-RT-01): `graph_facts` must
        already be the result of `KuzuGraphStore.get_manifestation`. Thin
        consumer of `iter_candidates` — collects every `ConceptCandidates`/
        `ConceptPairCandidates` it yields into one `RetrievalContext`, same
        shape and ordering as before this method was split in two."""
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
        above collects in full. Every concept's deep pool
        (`_search_deep_pools`) is searched before the first item is yielded.

        Runs one similarity search per query from `build_query_texts` (one
        per individual atomic concept, some carrying an exact-value text
        filter — see this module's docstring), grouped by concept (FR-RT-07)
        rather than merged into one shared pool: within a concept, hits are
        combined by Reciprocal Rank Fusion (each chunk's fused score is the
        sum of `1 / (_RRF_K + rank)`, 1-based rank within that specific
        query's own results, across every query *of that same concept* that
        surfaced it — never across a different concept's queries, which this
        module's docstring explains isn't a fair comparison and is exactly
        the crowding-out this grouping exists to prevent).

        Each concept's fused ranking is searched to `match_pool_size` depth
        but only its top `top_k` is *displayed* (FR-RT-07 unchanged) — the extra
        depth exists purely to detect concept-pair convergence (FR-RT-08) below
        the displayed cutoff, e.g. a passage ranked #1 for one concept and #9
        for another. A chunk's displayed score is its best (lowest-distance)
        individual match, for `min_score` filtering and for what a researcher
        actually sees.

        Concept pairs (FR-RT-08, FR-RT-09) are then built from every concept's full
        deep pool: two semantic concepts sharing a chunk, or a semantic
        concept sharing a chunk with a recognized exact-value filter token
        (proven via that token's `document_contains` filter, not similarity).
        Each pair's candidates are ranked by `_combined_score` and cut to
        `merge_top_k`.
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
        """Runs every query from `build_query_texts`, Reciprocal-Rank-Fusing hits
        *within* each concept's own queries only (never across concepts), to
        `match_pool_size` depth. Returns `(deep_hits_by_concept,
        filter_token_chunk_ids, all_hits_by_chunk_id)` — the first two
        structures `iter_candidates` built inline before this extraction; the
        third is every hit any query returned, before RRF trims each
        concept's own pool to `match_pool_size`. `retrieve_regions` needs
        that unfiltered map: an exact-token match's chunk can be a genuine
        filter hit (`document_contains` is a hard containment guarantee)
        without ever surviving into any *concept's* RRF-ranked pool — a real
        case is Genesis 21:5 ("hundred"), which never ranks highly enough
        for "child" on its own to make that concept's top `match_pool_size`,
        so resolving its coordinates only through `deep_hits_by_concept`
        would silently drop the match. Each concept's `dict[chunk_id,
        VectorHit]` preserves RRF-rank order (insertion order), so a caller
        taking its first `top_k` entries gets the same displayed slice
        `iter_candidates`'s `ConceptCandidates` would."""
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

        return deep_hits_by_concept, filter_token_chunk_ids, all_hits_by_chunk_id

    def retrieve_regions(self, graph_facts: GraphFacts) -> RegionQueryResult:
        """Region-centric retrieval (FR-RK-01–FR-RK-10):
        rolls up floor-clearing interpretant matches over contiguous windows
        of one source's segments, ranked by a specificity-weighted score.

        Uses the same underlying search as `iter_candidates`
        (`_search_deep_pools`); only what's aggregated and returned differs:
        a match is kept only if it clears `min_score` (FR-RT-14) — no ranking cutoff
        substitutes for it — then matches are grouped into regions by
        contiguous ordinal within `region_window_size` (FR-RK-02). Within a
        region, an interpretant that matched more than one of its segments
        keeps only its single best match (FR-RK-01, FR-RK-05) — summing every
        per-segment occurrence would let a passage repeating one token across
        many adjacent segments (e.g. a genealogy chapter repeating "hundred")
        inflate its score by simple repetition, exactly the list-like-passage
        failure mode ADR-004 already rejected at the ranking-formula level.
        That single best match still anchors to the specific segment it
        occurred at (FR-RK-09). A region is eligible when its count of distinct
        *concept* interpretants — an exact-token match is a literal-containment
        guarantee, not a semantic signal, and is excluded from this count so a
        common filter token can't make an otherwise-unmatched region eligible —
        reaches `region_min_interpretants`; the default of 1 makes an isolated
        strong match a valid, rankable region on its own (FR-RK-03)."""
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
        exact-value filter token it shares a chunk with (FR-RT-09). A pair of two
        filter tokens is never emitted — a filter token carries no score of
        its own (it's a guarantee of containment, not a similarity judgment),
        so there is nothing to rank such a pair by. Groups are sorted
        strongest-first by their own top candidate; see this module's
        docstring and plan.md's Risks on why that ordering is a display
        heuristic, not a claim that one group's score is commensurable with
        another's."""
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
        (FR-RK-04/FR-RK-06): `log(N / df(surface_form))`,
        `N` the total number of ingested segments and `df` the count of
        segments literally containing `surface_form` on whole-word boundaries
        (`ChromaVectorStore.document_frequency`, never a count derived from
        dense embedding scores — ADR-004 found that diffuse and misleading).
        `df` is floored at 1 (a surface form absent from the corpus is treated
        as at least as rare as one appearing exactly once, not infinitely
        rare) so this never divides by zero or takes `log(0)`."""
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
        varies by which concept or query surfaced it (only its similarity
        score does, which this method does not cache)."""
        cached = self._lookup_cache.get(hit.source_id)
        if cached is None:
            cached = self._graph_store.get_source(hit.source_id)
            self._lookup_cache[hit.source_id] = cached
        return cached


def _atomic_values(value: str) -> list[str]:
    """A comma-separated value (e.g. a Hebrew letter's `meaning`, "Monkey, eye
    of the needle") lists several distinct concepts sharing one curator-chosen
    `type`, not a single unified phrase — split it so each concept is searched
    entirely on its own. A value with no comma is already atomic and comes
    back as a one-item list; see this module's docstring for the concrete
    case this exists for."""
    return [part.strip() for part in value.split(",") if part.strip()]


def _filter_token_for(interpretant: Interpretant) -> _FilterToken | None:
    """The `_FilterToken` for an interpretant carrying a `query.directive ==
    "filter"` annotation, or `None` for any other interpretant. The search
    text (`as_token`) is authored directly by the curator (FR-CO-03, FR-RT-09) — there
    is no code-side value-to-word inference here."""
    if interpretant.query is not None and interpretant.query.directive == "filter":
        return _FilterToken(value=interpretant.value, as_token=interpretant.query.as_token)
    return None


def _is_skipped(interpretant: Interpretant) -> bool:
    """True for an interpretant carrying a `query.directive == "skip"`
    annotation (FR-RT-11) — excluded from retrieval entirely, unlike a `"filter"`
    interpretant, which still contributes a literal-text filter query."""
    return interpretant.query is not None and interpretant.query.directive == "skip"


def _extract_concepts(interpretants: tuple[Interpretant, ...]) -> list[str]:
    """Every interpretant's value, decomposed to one atomic concept per value
    (`_atomic_values`) — an interpretant carrying a `query.directive: "filter"`
    annotation is excluded here, since it's handled separately as a global
    filter (`_collect_filter_tokens`), not as a concept of its own; one
    carrying `"skip"` (FR-RT-11) is excluded outright, contributing no query of any
    kind. Properties (`Sign.properties`/`Manifestation.properties`) are never
    passed to this function at all — only `Manifestation.interpretants` and
    `IntersemioticInterpretant.target_interpretants` ever reach it."""
    concepts: list[str] = []
    for interpretant in interpretants:
        if _is_skipped(interpretant) or _filter_token_for(interpretant) is not None:
            continue
        concepts.extend(_atomic_values(interpretant.value))
    return concepts


def _collect_filter_tokens(interpretant_groups: list[tuple[Interpretant, ...]]) -> list[_FilterToken]:
    """Every recognized exact-value filter token (an interpretant carrying
    `query.directive == "filter"`) found anywhere across `interpretant_groups`
    — the manifestation's own interpretants, and every intersemiotic
    interpretant's `target_interpretants` — converted to a `_FilterToken` and
    deduplicated by `as_token`, order-preserved by first appearance. Collected
    globally rather than per-group (see this module's docstring): a real
    passage can combine a concept from one part of the graph with a filter
    token from an entirely different part, so the filter these become
    (`_fact_queries`) applies to *every* concept, not just the ones that
    happen to share a group with the token. The authored form (e.g. "100") is
    kept alongside the search form ("hundred") so it can surface as a pair
    member in its own right (FR-RT-09) rather than being discarded once the
    search text is derived."""
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
    query, plus — for every filter token recognized *anywhere* in the current
    `GraphFacts` (`filter_tokens`, global, not just this group's own) — one
    additional filtered variant per concept, combined with that token as a
    literal-text filter.

    Deliberately a boost, not a hard requirement: an earlier version made a
    filter token *replace* its group's concept queries with filtered-only
    versions, which silently returns zero results for any card where no
    single passage happens to combine the token and the concept — killing
    real candidates is worse than an occasional missed boost. Now every
    concept is always searched plainly (nothing is ever lost), and each
    filtered variant only adds an *additional* independent ranking that
    rewards a passage combining both signals — via Reciprocal Rank Fusion
    (`RetrievalPipeline.retrieve`), a passage matching both ranks higher than
    one matching only the concept, without excluding the latter. A group with
    no concepts of its own contributes no queries here — a lone filter token
    with nothing to filter is handled once, globally, by `build_query_texts`."""
    concepts = _extract_concepts(interpretants)
    queries = [_Query(text=concept) for concept in concepts]
    for token in filter_tokens:
        queries += [_Query(text=concept, filter_token=token) for concept in concepts]
    return queries


def _intersemiotic_query_texts(
    interpretant: IntersemioticInterpretant, filter_tokens: list[_FilterToken]
) -> list[_Query]:
    """One query per *individual atomic concept* about an intersemiotic
    interpretant's target — its own manifestation-level interpretants across
    every tradition it is manifested under (`target_interpretants`, e.g. its
    Sepher Yetzirah `foundation`). Already hydrated by
    `KuzuGraphStore._get_sign_intersemiotic_interpretants`, so this needs no
    extra graph fetch here. Never includes the target sign's or its
    manifestations' `properties` — properties are never used to build
    retrieval query text (FR-CO-03, FR-DM-04), at any scope, reached any way.

    Deliberately does *not* query the target's bare name (e.g. "Qoph") on its
    own — see this module's docstring TODO on why that's disabled for now."""
    return _fact_queries(interpretant.target_interpretants, filter_tokens)


def build_query_texts(graph_facts: GraphFacts) -> list[_Query]:
    """One query per individual atomic concept reachable from the queried
    sign (FR-CO-03): one per atomic concept in each interpretant of the sign's own
    manifestation, then for each intersemiotic interpretant (FR-DM-03, FR-SD-04), one
    per individual atomic concept about the target — see this module's
    docstring for why keeping every concept this isolated matters, for why
    there's no combined descriptive-identity query (a sign's canonical name, a
    manifestation's display name/denotation, and any properties at any scope
    aren't searched at all), and for why every recognized filter token
    anywhere in `graph_facts` becomes a filtered variant of *every* concept,
    not just the ones in its own group. `RetrievalPipeline.retrieve` embeds
    and searches every one, then merges the results by rank (RRF), not raw
    score, within each concept."""
    sign, manifestation = graph_facts.sign, graph_facts.manifestation
    interpretant_groups = [manifestation.interpretants]
    interpretant_groups += [interpretant.target_interpretants for interpretant in sign.intersemiotic_interpretants]
    filter_tokens = _collect_filter_tokens(interpretant_groups)

    queries = _fact_queries(manifestation.interpretants, filter_tokens)
    for interpretant in sign.intersemiotic_interpretants:
        queries += _intersemiotic_query_texts(interpretant, filter_tokens)

    if not queries:
        # No concept anywhere to attach a filter token to (e.g. a sign whose
        # only fact is a bare exact-value interpretant) — search each token's
        # search form on its own rather than silently dropping it (a filter
        # with nothing to filter isn't useful, but the token itself may still
        # be meaningful search text). Not tagged with `filter_token=`: there's
        # no concept for it to pair against, so it can't participate in
        # FR-RT-08/FR-RT-09 convergence anyway.
        queries += [_Query(text=token.as_token) for token in filter_tokens]

    return [query for query in queries if query.text]


def _filter_token_surface_forms(graph_facts: GraphFacts) -> dict[str, str]:
    """Maps every recognized filter token's curator-authored `value` (the
    form used as `Match.interpretant`, e.g. `"100"`) to its searched
    `as_token` (the literal form actually present in the corpus, e.g.
    `"hundred"`) — specificity weighting for a token interpretant must use
    the searched form (plan.md area E), not the authored one, since that's
    what `document_frequency` actually counts."""
    sign, manifestation = graph_facts.sign, graph_facts.manifestation
    interpretant_groups = [manifestation.interpretants]
    interpretant_groups += [interpretant.target_interpretants for interpretant in sign.intersemiotic_interpretants]
    return {token.value: token.as_token for token in _collect_filter_tokens(interpretant_groups)}


def _cluster_ordinals(ordinals: set[int], window_size: int) -> list[list[int]]:
    """Chains eligible ordinals (already known to be from the same source)
    into contiguous regions: sorted ascending, an ordinal joins the region in
    progress when it is within `window_size` of that region's most recent
    ordinal, else it starts a new region (FR-RK-02) — so a region can span more
    than `window_size` end-to-end when matches occur in a close-packed chain,
    the same way the region rollup's Genesis 20:18-21:6 finding
    crosses more than one fixed-size window."""
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
    `"Genesis 21:5–6"`, matching plan.md's worked contract); otherwise the two
    full locators are joined, still unambiguous."""
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
    at zero per component before multiplying (FR-RT-08). `_similarity_score` is
    `1 - cosine_distance`, which spans `[-1, 1]`, not `[0, 1]` — a negative
    component would otherwise make the root complex, and a passage
    anti-correlated with one member of a pair has no conjunctive strength to
    reward anyway.

    Geometric rather than arithmetic because convergence is conjunctive, not
    additive: a passage scoring `(0.90, 0.20)` and one scoring `(0.57, 0.53)`
    share an identical sum and mean, yet only the second genuinely sits at
    the intersection of both concepts — the first is a strong match on one
    concept that merely reached the other's deep matching pool. The
    geometric mean tells them apart (`0.42` vs `0.55`); see this module's
    docstring and `ConceptPairCandidates` for the full argument."""
    clamped = tuple(max(0.0, score) for score in scores)
    return math.prod(clamped) ** (1.0 / len(clamped))
