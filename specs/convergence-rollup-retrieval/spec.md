# Convergence Rollup Retrieval — Spec

## Problem

A sign contributes a set of interpretants of mixed kinds — exact tokens (numbers, letters, fixed names) and open concepts. The evidence of interest is any region of a corpus where one or more of a sign's interpretants match strongly. A region where several distinct interpretants converge is of particular interest, but a region matched strongly by a single interpretant is itself a valid result and must not be discarded for lacking company.

Two failure modes shape the model. First, when several interpretants do converge, the contributing signals are frequently spread across adjacent structural units of one source rather than co-located in one fixed-size chunk, so a model that only detects multiple interpretants landing on a single chunk misses them. Second, a scoring model that ranks by match strength normalized within a query — rather than by an absolute measure — manufactures apparent matches: in a corpus that does not contain an interpretant at all, the best-of-noise segment is stretched to look like a strong match, and a summed score then over-rewards long, list-like regions carrying a weak trace of many interpretants.

This spec defines a retrieval and ranking model that (a) segments a corpus along its own structure rather than by fixed word count, (b) matches each interpretant independently and live, gating concept matches by an absolute similarity floor, (c) aggregates the surviving matches over a configurable region of contiguous segments — which may be a single segment — and (d) ranks regions by a specificity-weighted score in which a region matched by more, or rarer, interpretants ranks higher, while a region matched by a single strong interpretant remains a valid, rankable result.

## Terminology

- **segment**: The atomic retrieval unit — one structurally-bounded piece of a source (e.g. a single scripture verse or numbered section), carrying exact structural coordinates and a stable ordinal position within its source. Replaces the fixed word-count chunk as the unit that is embedded and matched.
- **structural coordinates**: The source-relative reference locating a segment (e.g. source id, chapter/section, verse/ordinal), sufficient to render a human-readable locator and to determine whether two segments are contiguous within the same source.
- **match floor**: An absolute lower bound on a concept interpretant's similarity, below which the interpretant is treated as not matching that segment. It is an absolute threshold, not a rank or a within-query normalized quantity.
- **interpretant match**: One interpretant's evidence for one segment — a similarity score for a concept interpretant that clears the match floor, or a containment result for an exact-token interpretant.
- **convergence unit** (a.k.a. **region**): A bounded span of contiguous segments within a single source over which interpretant matches are aggregated (a single segment, a structural section, or a sliding window of N consecutive segments). Scoring happens at this granularity.
- **isolated match**: A region in which exactly one distinct interpretant matches. It is eligible and rankable like any other region.
- **convergence count**: The number of distinct interpretants matching within a region.
- **specificity weight**: A per-interpretant weight derived from how many units of the corpus contain a surface form of that interpretant. A rarer surface form yields a higher weight.
- **convergence score**: A region's rank value — the specificity-weighted sum of the best per-interpretant match strength within the region.

## Goals

- Segment corpora along their own structure, with exact structural coordinates, so aggregation boundaries are exact and no signal leaks between adjacent structural units.
- Surface both isolated strong interpretant matches and multi-interpretant convergences in one ranking. Convergence of several interpretants raises a region's rank, but is never a precondition for a region to appear.
- Suppress fabricated matches with an absolute match floor, so that a corpus lacking a sign's interpretants yields few or no matches rather than a confident best-of-noise ranking.
- Detect convergence of an arbitrary number of a sign's interpretants over a contiguous region, independent of which single segment any one interpretant matched.
- Rank by a specificity-weighted score that lets a rare, discriminating interpretant count for more than a ubiquitous one, and that reflects absolute match quality rather than within-query normalization.
- Keep matching live and per-interpretant at query time, so interpretants may be added, edited, or tested ad hoc without any precomputation step.
- Preserve per-interpretant attribution in results — each ranked region reports which interpretants matched it and each one's best match — so a result remains inspectable and filterable.
- Remain domain-agnostic: no domain-specific structural notion (chapter, verse, pericope) is baked into the core; structure comes from the corpus's own declared coordinates.

## Non-goals

- Lexical relevance ranking (BM25/SPLADE) and rank-fusion (e.g. RRF) as a matching mechanism. The lexical channel is used only for exact-token containment filtering and for the specificity-weight document-frequency counts, not to rank regions.
- Precomputing an interpretant-to-segment match matrix. Matching is performed live per query.
- A hosted or distributed vector-search backend. Retrieval runs against the local vector store.
- Requiring multi-interpretant convergence for a result. A single interpretant clearing the match floor produces a rankable region.
- Multi-sign / spread queries (unchanged from `symbol-interpretation-core` Non-goals).
- Automatic detection of semantic region boundaries (topic segmentation). A region is a contiguous span defined by structural coordinates and a window size, not by inferred topic shifts.

## Functional requirements

### Segmentation

- FR1: The document loader segments a source along its own declared structure into atomic segments (one segment per smallest structural unit the source declares, e.g. a verse or a numbered section), rather than into fixed word-count windows. A segment never spans a structural boundary of its source, and no segment overlaps another.
- FR2: Each segment records exact structural coordinates and a stable ordinal position within its source, sufficient to (a) render a human-readable locator and (b) determine contiguity — whether one segment immediately follows another in the same source. Any structural-label prefix (e.g. a leading section number) is excluded from the segment's matchable text so that it neither influences embedding nor produces spurious token containment.
- FR3: Segmentation is content-hash idempotent per source (as in `symbol-interpretation-core` FR23): re-ingesting an unchanged source is a no-op; re-ingesting a changed source replaces that source's segments.

### Matching

- FR4: Each interpretant of the queried sign (including interpretants reachable via intersemiotic interpretants, per `symbol-interpretation-core` FR8) retrieves its matches independently and at query time — no interpretant's matches are precomputed, and adding or altering an interpretant changes results on the next query with no separate build step.
- FR5: A concept interpretant matches segments by embedding similarity, using the embedding model only (no generation model), consistent with `symbol-interpretation-core` FR29.
- FR6: A concept interpretant matches a segment only when its similarity clears a configurable absolute match floor; below the floor it contributes no match. The floor is an absolute similarity threshold, evaluated per segment against the raw similarity — never a rank cutoff and never a value normalized across the current query's results — so that a corpus not containing the concept yields no match for it rather than a best-of-noise match.
- FR7: An exact-token interpretant (one carrying a `query.directive: "filter"` annotation, per `symbol-interpretation-core` FR8/FR28) matches segments by literal containment of its token rather than by similarity. Containment is evaluated on whole-word boundaries (a token does not match inside a larger word or number) and supports normalization so that a token and its corpus surface forms are treated as equivalent (e.g. a numeric value and its spelled-out forms). A containment match contributes membership, not a similarity score, and is not subject to the match floor.
- FR8: An interpretant carrying `query.directive: "skip"` (per `symbol-interpretation-core` FR30) contributes no match of any kind.

### Convergence rollup

- FR9: Interpretant matches are aggregated to the convergence unit: for each region and each interpretant, the region retains that interpretant's single best surviving match within it (best floor-clearing similarity for a concept interpretant; presence for an exact-token interpretant).
- FR10: A region's convergence is defined over contiguous segments of a single source. The convergence-unit granularity is a configurable parameter of the query — a single segment, a structural section, or a window of N consecutive units — not a fixed constant.
- FR11: A region is eligible to be ranked when at least a configurable minimum number of distinct interpretants match within it. The minimum defaults to one: a region matched by a single interpretant (an isolated match) is eligible and rankable. Convergence is therefore a ranking signal, not an eligibility gate. A region's reported convergence count is the number of distinct interpretants matching within it.

### Specificity-weighted ranking

- FR12: Each interpretant carries a specificity weight derived from the document frequency of its surface form across the corpus — the number of corpus units containing that surface form — such that a rarer surface form yields a strictly higher weight, and a ubiquitous one a lower weight.
- FR13: A region's convergence score is the sum, over the interpretants matching within it, of each interpretant's specificity weight multiplied by that interpretant's best match strength within the region. A concept interpretant's match strength is its raw floor-clearing similarity; an exact-token interpretant's is a fixed presence value. Regions are ranked by this score, descending. Because the score sums over matching interpretants, a region matched by more distinct interpretants tends to rank above one matched by fewer of comparable strength — convergence raises rank as an emergent property of the sum, not through a separate gate.
- FR14: The specificity weight is computed from literal surface-form frequency, not from embedding-similarity score distributions. Match strength entering the score is raw floor-clearing similarity, not a value min-max normalized within the query's results, so absolute match quality is preserved and comparable across queries and corpora.

### Results and attribution

- FR15: A query returns a ranked list of regions. Each region reports its structural locator, its convergence count and convergence score, the constituent interpretants that matched it (one or more), and, per interpretant, that interpretant's best match within the region (its similarity score, or a containment indication for an exact-token interpretant).
- FR16: For each region, the output includes the verbatim text of the constituent segment(s) that carried the matches, addressable by their structural coordinates — not merely a locator or a marker (consistent with `symbol-interpretation-core` FR13). A segment's verbatim text appears once per region regardless of how many interpretants matched it.
- FR17: Each interpretant's match anchors to the specific constituent segment that carried it (by that segment's structural coordinates), so a result reveals not only that an interpretant matched the region but exactly where within it — enabling a consumer to navigate directly to the matching segment rather than re-scanning the region.
- FR18: Results preserve per-interpretant attribution as first-class data so a consuming interface (per `query-viewer-facet-redesign`) can display which interpretants matched, count them, filter by them, and navigate to each one's matching segment — without recomputation.

## Relationship to existing specs

- Evolves the convergence model of `symbol-interpretation-core` FR24/FR27/FR28: per-concept independent retrieval (FR24) is retained; the two-concept-pair convergence group (FR27) and its exact-filter membership (FR28) are generalized into an N-interpretant, specificity-weighted region ranking (FR9–FR18 here) in which multi-interpretant convergence is a ranking signal rather than a required pairing. The exact-token filter (FR28) and skip (FR30) directives are carried forward unchanged in meaning.
- Supplies the fragment/facet data consumed by `query-viewer-facet-redesign`: a ranked region maps to a displayed fragment, its constituent interpretants to that fragment's matches, and its convergence count to the displayed badge (which may read one).
- Retains `symbol-interpretation-core`'s domain-agnosticism guardrail (FR17): the structural, contiguity, match-floor, and surface-form notions here are defined generically and driven by corpus-declared data and query-level parameters, with no domain-specific literal in the core.
