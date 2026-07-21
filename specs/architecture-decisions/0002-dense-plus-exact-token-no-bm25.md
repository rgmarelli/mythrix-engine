# ADR 0002 — Two matching channels: dense + exact-token, no BM25

- **Status**: Accepted
- **Date**: 2026-07-21
- **Realized by**: `specs/symbol-interpretation-core/spec.md` FR35–FR37; Non-goals

## Context

Interpretants are of two irreducibly different kinds:

- **Concepts** (`laughter`, `kingdom`, `Fish`) — open meanings that must match
  *semantically*; the corpus rarely contains the word itself.
- **Exact tokens** (`100`/`hundred`, `Scorpio`, a Hebrew letter-name) — where the
  point is literal presence, and a *near*-match is wrong. "A hundred years old"
  (Genesis 21:5) is the match; a semantically-similar passage about old age is not.

The obvious question was whether to add **BM25** (lexical relevance ranking) as a
third channel and fuse the rankings (e.g. RRF), the standard "hybrid search"
recipe. Two findings settled it:

1. **BM25 gave only marginal, situational gains.** On the Genesis benchmark BM25
   helped `laughter` slightly and *hurt* `child`; dense similarity alone already
   surfaced the target once rolled up. The lexical *ranking* signal did not earn
   its complexity.
2. **BM25 is not available in the deployment anyway.** Chroma 1.5.9 exposes a
   native BM25/sparse `search()` API, but it is **cloud/distributed-only**; the
   local `PersistentClient.search()` raises `NotImplementedError: Search is not
   implemented for Local Chroma`. The local client offers only `query()`/`get()`
   with `where_document` (`$contains`/`$regex`). Building on cloud-only BM25 would
   contradict the local-store constraint ([ADR 0005](0005-vector-store-chroma-and-lexical-store-path.md)).

A separate but related point: `$contains` is **substring**, not word-bounded. It
false-matched the numeric token `50` inside section labels `50.`/`150.` in the
Bahir test. Exact-token matching must be **whole-word** (`$regex \bfifty\b`) and
must **normalize** numeral↔spelled-out forms (`100 ↔ hundred`).

## Decision

Exactly two matching channels, no BM25 and no rank-fusion:

- **Dense (embedding similarity)** for concept interpretants.
- **Exact-token containment** for `filter`-directive interpretants — whole-word,
  normalized, evaluated as literal presence. A containment match contributes
  *membership*, not a score.

The lexical layer is used **only** for (a) this exact-token containment and (b) the
document-frequency counts behind specificity weighting
([ADR 0004](0004-absolute-floor-and-lexical-specificity-ranking.md)) — never to
*rank* regions.

## Consequences

- No RRF, no score-fusion tuning, no sparse index to maintain. The ranking signal
  is dense similarity plus specificity weight; the lexical channel is a boolean
  filter and a statistics source.
- Exact tokens are a hard guarantee ("this passage literally contains *hundred*"),
  which is exactly what a number or a fixed name needs, and which a graded ranker
  would blur.
- Word-bounded + normalized containment is a firm requirement, not an
  optimization: naive substring is demonstrably wrong.
- If a future need for lexical *ranking* emerges, it is a new ADR — this one
  explicitly scopes the lexical channel to filter + statistics.

## Alternatives considered

- **Hybrid dense + BM25 with RRF.** Rejected: marginal/again-situational benefit,
  cloud-only in this stack, and added fusion complexity for no measured win.
- **Regex/`$contains` as the only channel.** Rejected: it is a boolean filter with
  no notion of semantic match, so open concepts (`laughter`, `kingdom`) would be
  unreachable.
- **`$contains` (substring) for tokens.** Rejected: word-boundary false positives
  (`50`→`150`); replaced by `$regex` word-bounded matching.
