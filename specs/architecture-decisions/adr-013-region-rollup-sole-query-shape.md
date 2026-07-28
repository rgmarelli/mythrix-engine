# ADR-013 — Region rollup is the sole query result shape

- **Status**: Accepted
- **Date**: 2026-07-28
- **Supersedes**: the concept-pair scoring decision of [ADR-007](adr-007-rrf-fusion-and-geometric-mean-pair-scoring.md) (its third Decision bullet). ADR-007's within-concept RRF merging and bare-target-name rule are unaffected and remain in force.
- **Realized by**: [retrieval.md](../retrieval/retrieval.md) FR-RT-01, FR-RT-05, FR-RT-06; [ranking.md](../retrieval/ranking.md) FR-RK-01+

## Context

`RetrievalPipeline` grew two aggregators over one matching engine. Both consume
the same `_search_deep_pools` output; they differ only in what they aggregate
and return:

- `retrieve()` → per-concept candidate groups ([retrieval.md](../retrieval/retrieval.md) FR-RT-07) plus
  per-concept-pair groups (FR-RT-08), scored by the geometric mean of the pair's
  two similarities (ADR-007), at **chunk** granularity.
- `retrieve_regions()` → one flat, globally-ranked list of contiguous segment
  regions, scored by a lexical-IDF-weighted sum over each region's best match
  per interpretant ([ADR-001](adr-001-structural-segmentation-and-region-rollup.md), [ADR-004](adr-004-absolute-floor-and-lexical-specificity-ranking.md)).

The second was introduced because the first did not work at real corpus scale.
The empirical finding behind ADR-001 was that convergence is not a per-chunk
fact: for the Sun/Qoph benchmark, the signals scatter across adjacent verses of
one narrative ("laughter" at Genesis 21:6, "a hundred years old" at 21:5, barren
wombs at 20:18), so per-chunk pairing ranked the target around #600-757 while
rolling up to the chapter/pericope lifted it to #1-2. ADR-004 then established
that ranking must weight each interpretant by **lexical** rarity, and that an
isolated match is a first-class, rankable result rather than something gated
behind convergence — convergence became an emergent ranking boost, not an
eligibility criterion or a separate result group.

That reframing left the pair branch with no role, but it stayed reachable
through `mythrix query`, the only surface still calling `retrieve()`. The API,
the web viewer, and the agent's tools have used `retrieve_regions()` throughout.
Keeping both meant two result vocabularies, two scoring theories, and two sets
of models describing the same retrieval.

## Decision

`retrieve_regions()` is the only aggregation the retrieval pipeline exposes. The
per-concept and per-concept-pair result shape is retired, along with the
`mythrix query` command that was its only consumer.

Concretely:

- Convergence is expressed as it is under ADR-004: a region's score sums the
  specificity-weighted strength of each distinct interpretant matching within
  it, so more converging interpretants rank higher, and `convergence_count`
  reports how many did. There is no separate convergence result group.
- Pair membership is no longer enumerated as its own object. A region's
  `matches` carries every interpretant that matched, its kind, its score, and —
  via `Match.segment_ordinal` — the specific segment it hit, so what converged
  and where remains fully readable from the result.
- A concept-pair combined score is no longer computed. The geometric mean of
  ADR-007 has no counterpart in the region score, which is additive by
  construction.
- The structured, auditable output obligation moves from the CLI's `--json`
  mode to the `/api/query` region payload.

## Consequences

- One result vocabulary. A consumer learns regions, segments, and matches;
  nothing has to explain when a result is a concept group, a pair group, or a
  region, or why two scores on screen are not comparable with each other.
- **Conjunctive scoring is given up, not merely relocated.** The geometric mean
  was chosen precisely because it separates `(0.90, 0.20)` from `(0.57, 0.53)` —
  a lopsided single-concept match from a genuine intersection. A weighted sum
  does not make that distinction; it accumulates. ADR-004's lexical-IDF
  weighting addresses the same failure mode (a weak trace of everything scoring
  well) by a different mechanism, and was the one validated at real corpus
  scale, but the two are not equivalent. A future question of the form "show
  only regions strong on *both* interpretants" is not expressible against the
  current region score.
- Should that question become live, the answer is to evaluate a conjunctive
  strategy **against the region unit**, as a new decision. Restoring the retired
  branch would not serve it: that branch scores chunks, the granularity ADR-001
  rejected on evidence.
- Retirement is inexpensive to reverse for its inputs' sake:
  `_search_deep_pools` — which produces everything the pair branch consumed —
  is untouched by this decision. What is discarded is roughly sixty lines of
  aggregation plus its models, not any matching or fusion capability.
- Retrieval settings that only the retired branch read (`retrieval_top_k`,
  `merge_top_k`) are removed. `retrieval_match_pool_size` stays: it governs
  `_search_deep_pools`, which both branches always shared.
- FR-RT-07, FR-RT-08, and FR-RT-09 are retired. FR-RT-09 additionally carried
  the `"filter"` directive's membership-not-similarity guarantee, which the
  surviving region-path requirements (FR-RT-15, FR-RT-18, FR-RT-19) referenced
  rather than restated; they now state it directly.

## Alternatives considered

- **Keep both aggregators, drop only the CLI command.** Rejected: it preserves
  the duplication this decision exists to remove, leaving `retrieve()`,
  `_build_pair_candidates`, six models, and two config knobs reachable by
  nothing. Unused code that still compiles is indistinguishable from supported
  behavior to the next reader.
- **Port pair display onto regions now** (emit pair groups over region matches
  alongside the ranked list). Rejected as speculative: no surface asks for it,
  and ADR-004 already established convergence as a ranking signal rather than a
  grouping. If it is wanted later it is an additive feature over a stable
  region model, not a reason to keep the chunk-level branch alive meanwhile.
- **Preserve the geometric mean as an alternative region ranking strategy in
  this change.** Rejected as out of scope: it is a ranking decision requiring
  its own benchmark against the real corpus, not a byproduct of removing a dead
  surface. Recorded here as open future work instead.
