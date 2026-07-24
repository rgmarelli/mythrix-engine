# ADR-008 — Retrieval tuning defaults: pool depth and match floor calibration

- **Status**: Accepted
- **Date**: 2026-07-24
- **Realized by**: `Settings.retrieval_match_pool_size`, `Settings.retrieval_min_score` (`api/src/mythrix/core/config.py`); [retrieval.md](../retrieval/retrieval.md) FR-RT-08, FR-RT-14

## Context

Two `Settings` defaults for the same retrieval pipeline needed a specific
number, not just a design ([ADR-004](adr-004-absolute-floor-and-lexical-specificity-ranking.md)
already settled *that* an absolute floor is used, and *that* pair detection
runs over a deeper pool than what's displayed — this ADR settles *which*
values).

**Pool depth.** `retrieval_match_pool_size` originally defaulted to `30`,
fit against a ~1,621-fixed-word-chunk corpus, where it covered close to 2% of
the collection. Once the corpus was re-segmented along verse/section
boundaries into ~36,000 segments, that default was never re-measured against
the new scale. A concrete failure surfaced against The Sun's `child` concept
(Rider-Waite tradition): Genesis 21:8 ("And the child grew...") is the only
verse in the Abraham/Isaac narrative literally containing "child" (21:5/21:6
say "son"/"a hundred years old"/"laughter" instead), and it ranked 31st raw —
one past the old pool depth of 30 — silently dropping `child` from the
Genesis 21 region's convergence while unrelated census-list passages (which
happened to combine several other concepts weakly) outranked it. Sweeping
`30`/`60`/`100`/`150`/`250` found `100` the shallowest depth that consistently
recovered that match, with no further improvement past `100` and negligible
added query latency.

**Match floor.** `retrieval_min_score` originally defaulted to `0.0`. Against
a real query (The Sun/Rider-Waite, `nomic-embed-text`, the 1,621-chunk
corpus), the distribution of match scores across all retrieved fragments is a
smooth, single-humped curve from ~0.36 to ~0.55 with no natural gap between
"real" and "noise" matches (mean/median both ~0.44). At `0.0`, every
candidate within `retrieval_match_pool_size` counts toward convergence
regardless of strength, which let a long, topically broad chunk (Deuteronomy
33, an imagery-dense passage) register as converging on 8 of 10 interpretants
at once — none individually strong (each below or barely at that
interpretant's own weakest top-6 corpus-wide score).

## Decision

- `retrieval_match_pool_size` defaults to `100`.
- `retrieval_min_score` defaults to `0.6` — comfortably above the observed
  noise median, favoring precision over recall without claiming a
  principled "correct" cutoff exists in the data.
- Both remain overridable per-request (`/api/query`'s `min_score` param,
  `mythrix query --min-score`) or per-deployment (`MYTHRIX_*` env vars),
  since both were calibrated against one embedding model
  (`nomic-embed-text`) and one corpus scale, not derived from a formula.

## Consequences

- Neither value is guaranteed optimal for a different embedding model or a
  corpus at a substantially different scale — a swap or a large corpus
  change should re-run this kind of sweep rather than assume these numbers
  still hold.
- `0.6` trades recall for precision; a use case that wants to see more
  borderline candidates should override it per-request rather than treat it
  as universal truth.
- `retrieval_match_pool_size=100` costs additional Chroma searches per query
  (more candidates fetched), not additional embedding or generation cost —
  query embeddings are computed once regardless (FR-RT-10).

## Alternatives considered

- **Leaving `retrieval_match_pool_size` at `30`.** Rejected: silently dropped
  a genuine match once the corpus was re-segmented to a finer granularity
  (the Genesis 21:8 case above).
- **`retrieval_min_score = 0.0` (no floor beyond pool depth).** Rejected: let
  a long, topically diffuse passage falsely register as a multi-concept
  convergence purely by touching many concepts weakly (the Deuteronomy 33
  case above).
