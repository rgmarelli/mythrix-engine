# ADR 0003 — Live, per-interpretant matching; no precomputed match matrix

- **Status**: Accepted
- **Date**: 2026-07-21
- **Realized by**: `specs/symbol-interpretation-core/spec.md` FR34; Non-goals

## Context

An appealing optimization for convergence retrieval is to **precompute** an
interpretant→segment match matrix at ingest: embed every interpretant of every
sign once, store the top segments, and answer queries by lookup. It would make
queries cheap and make convergence a simple set-intersection.

It does not fit how this system is actually used. The author is **researching the
symbolism itself**: interpretants are added, edited, and removed constantly, and
*ad-hoc* interpretants are tested that do not live in any committed sign YAML at
all ("what if Qoph also meant X?"). A precomputed matrix would be stale the moment
an interpretant changed, and could not answer a query for an interpretant that was
never ingested. The whole point is to try new interpretants and see results
immediately.

There is also a scoring reason. Matching must be gated by an **absolute similarity
floor** and weighted by **live corpus statistics**
([ADR 0004](0004-absolute-floor-and-lexical-specificity-ranking.md)); baking match
decisions into a precomputed table would freeze those thresholds and statistics at
ingest time.

## Decision

Match **live at query time**, **independently per interpretant**:

- Each interpretant of the queried sign (including those reached via intersemiotic
  interpretants) runs its own retrieval — its own dense search or its own
  containment filter — against the full corpus. No interpretant's matches are
  precomputed.
- Adding, editing, or removing an interpretant changes results on the **next
  query**, with no build step.
- Each interpretant gets its own retrieval budget; hits are **not** merged into one
  shared pool before a cutoff (that would let a strong interpretant crowd out a
  rare one). Convergence is computed *after*, by rollup.

The **one thing that may be precomputed is corpus-level term statistics** (a
document-frequency table for specificity weighting). That is static corpus data
refreshed on ingest — *not* interpretant-match precompute — and it is the natural
way to keep IDF cheap at scale.

## Consequences

- Immediate iteration on interpretants — the core research workflow — is
  preserved. Ad-hoc interpretants outside the committed models work identically to
  committed ones.
- Query cost scales with (number of interpretants × corpus search cost). For a
  huge corpus this is the main performance pressure and is what the vector store
  must absorb ([ADR 0005](0005-vector-store-chroma-and-lexical-store-path.md)).
- Thresholds and specificity weights are always computed against the *current*
  corpus and *current* interpretant set — no stale-matrix class of bugs.
- The "no precompute" rule is specifically about **matches**. Confusing it with
  "no derived data at all" would forbid the df table, which is allowed and wanted.

## Alternatives considered

- **Precomputed interpretant→segment matrix.** Rejected: incompatible with live
  editing and ad-hoc interpretants; freezes floors and statistics.
- **Merge all interpretant hits into one pool, then cut.** Rejected: destroys
  per-interpretant budgets and lets common interpretants bury rare, discriminating
  ones before convergence is even computed.
