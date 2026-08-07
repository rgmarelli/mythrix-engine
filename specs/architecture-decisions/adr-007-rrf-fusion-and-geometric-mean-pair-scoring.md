# ADR-007 — Rank-based fusion within a concept; geometric mean for pair scores

- **Status**: Accepted; pair scoring superseded by [ADR-013](adr-013-region-rollup-sole-query-shape.md)
- **Date**: 2026-07-24
- **Realized by**: [retrieval.md](../retrieval/retrieval.md) FR-RT-07, FR-RT-08 (both retired, see [ADR-013](adr-013-region-rollup-sole-query-shape.md)); [corpus.md](../retrieval/corpus.md) FR-CO-03

## Context

A single concept can be searched by more than one query — its plain value, plus
one filtered variant per globally-recognized exact-value token
([ADR-002](adr-002-dense-plus-exact-token-no-bm25.md)) — and these must be
merged into one ranked list per concept. Separately, a concept-pair candidate
carries two independent similarity scores that must collapse into one combined
score.

A real case (the Sun, corresponding to the Hebrew letter Qoph) drove both
decisions. Qoph's Sepher Yetzirah foundation, "laughter", is the concept that
should surface Genesis 21:5. Searched alone, it ranked that passage #4 of
~1600 chunks. Once merged with Qoph's other queries — including a query for
the target letter's own bare name, "Qoph" — by comparing raw cosine scores
across queries, the correct match dropped out of the visible results entirely:
"Qoph" (a bare proper name) scored systematically higher across the board than
"laughter", not because it was more relevant, but because proper nouns sit
closer to generic ceremonial/priestly vocabulary in the embedding space than
the true match did. Raw-score comparison across differently-distributed
queries is not a fair merge.

A second, separate finding concerned scoring a concept-pair candidate.
Averaging or summing a pair's two per-concept scores cannot distinguish a
passage scoring `(0.90, 0.20)` from one scoring `(0.57, 0.53)` — identical sum
and mean — yet only the second genuinely sits at the intersection of both
concepts; the first is a strong single-concept match that merely also reached
the other concept's deep matching pool.

## Decision

- **Within a concept**, every one of its queries is embedded and searched
  independently, then merged by Reciprocal Rank Fusion (Cormack et al., 2009):
  each chunk's fused score is the sum of `1 / (k + rank)` (1-based rank within
  that query's own results, `k = 60`) across every query of that same concept
  that surfaced it. Cross-query merging is rank-based, never a comparison of
  raw similarity magnitudes.
- **An intersemiotic interpretant's target sign's bare canonical name is never
  issued as its own query**, for any relationship, regardless of domain. This
  is a blanket rule, not scoped to Hebrew letters specifically — the failure
  mode (a bare proper noun scoring well for reasons unrelated to meaning) is
  generic to embeddings, not particular to this symbol system.
- **A concept-pair's combined score is the geometric mean of its two
  per-concept similarity scores**, each clamped at zero first (similarity is
  `1 - cosine_distance`, which can be negative). An interpretant reached via an
  exact-value filter contributes membership but no score to this mean — it is
  a containment guarantee, not a similarity judgement
  ([ADR-002](adr-002-dense-plus-exact-token-no-bm25.md)).

## Consequences

- A query with a differently-shaped score distribution (e.g. a bare proper
  noun) can no longer dominate a merge regardless of relevance.
- Disabling the bare target-name query is a blanket, corpus-agnostic rule for
  now, and it discards a real signal in a corpus that would discuss those
  names directly and meaningfully — e.g. Psalm 119's letter-headed stanzas, or
  a Kabbalistic corpus (Sepher Yetzirah, Bahir) discussing the names
  themselves. Making this corpus-aware or per-relationship-type is open future
  work, not resolved by this ADR.
- The geometric mean only distinguishes lopsided from genuine convergence
  because pairs are detected over a deeper pool than the one displayed
  (`match_pool_size` vs `top_k`, FR-RT-08): at display depth alone, most
  co-occurring pairs are already decent on both dimensions, so the distinction
  would rarely matter.
- Scores remain comparable only within a pair group (both rows scored by the
  same two queries); they are not comparable across groups, for the same
  reason raw cross-query comparison was rejected above.

## Alternatives considered

- **Raw cosine score comparison across queries for within-concept merging.**
  Rejected: buries correct matches when a query's score distribution differs
  from another's for reasons unrelated to relevance (the Qoph/"laughter" case).
- **Keeping the bare target-name query enabled once RRF was in place.**
  Rejected: RRF fixes cross-query comparability, but the name query still
  tends to rank spuriously well within its own results, so it continued
  contributing noise even under rank-based fusion.
- **Arithmetic mean or sum of a pair's two per-concept scores.** Rejected:
  identical for cases that are genuinely distinguishable (`(0.90, 0.20)` vs
  `(0.57, 0.53)`); only the geometric mean separates a lopsided single-concept
  match from a true intersection.
