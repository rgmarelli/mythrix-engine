# ADR-001 — Structural segmentation with region rollup

- **Status**: Accepted
- **Date**: 2026-07-21
- **Realized by**: [corpus.md](../retrieval/corpus.md) FR-CO-05–FR-CO-07; [ranking.md](../retrieval/ranking.md) FR-RK-01–FR-RK-03

## Context

A query is one *sign* whose *interpretants* (meanings, a number, a letter-name, a
constellation) are matched against a corpus. The evidence we care about is where
those interpretants land — sometimes on one passage, more often scattered across
adjacent passages of a single narrative.

The driving benchmark: the interpretants of Qoph — `child`, `laughter`, `hundred`
— point at the Abraham/Isaac story. But that is **not a single-passage fact**. In
the Douay-Rheims text the signals are spread across neighbouring verses that even
cross a chapter boundary:

- `child` (Isaac) and `laughter` → Genesis 21:6
- `hundred` (*"a hundred years old"*) → Genesis 21:5
- barren wombs → Genesis 20:18

The original loader made this worse: it cut the corpus into **fixed ~650-word
chunks** and tagged each with a single **chapter** label (`Genesis 20`,
`Genesis 21`). Those windows straddle chapter ends, so signal bled between
unrelated passages, and a passage-level convergence detector never saw all three
interpretants together. Measured effect of chunk size on the target's rank
(specificity-weighted): Genesis 21 ranked **431st at 650-word chunks → 32nd at
250-word → 3rd at 150-word**. Smaller, cleaner units were strictly better.

## Decision

Split the two concerns that the fixed-chunk design had conflated:

1. **Segment fine, along the source's own declared structure** — one segment per
   verse (or per numbered section, for a text like the Bahir), never a fixed
   word-count window. Segments never overlap and never cross a structural
   boundary. Each carries exact structural coordinates (`source, chapter, verse`)
   and a stable ordinal position. The structural label itself (`2:6.`) is stripped
   from the matchable text.
2. **Converge coarse, by rolling up into a region** — a *region* is a run of
   *contiguous* segments (a window of N, or a section). An interpretant counts as
   matching the region if it matches **any** segment inside it; the region keeps
   that interpretant's best match. Convergence is scored at the region level.

Segmentation decides *where each interpretant matches*; rollup decides *where they
converge*. Region granularity is a per-query parameter.

## Consequences

- Verse is the clean floor of the "smaller is better" trend — zero cross-boundary
  bleed, exact aggregation boundaries.
- A verse-level **sliding window forms regions by ordinal contiguity, ignoring
  chapter labels**, so it can build the region `Genesis 20:18–21:6` that the
  interpretants actually occupy — something chapter-labelled chunks could only
  approximate with an awkward 2-chapter pericope rollup. Verse + rollup is
  therefore *more* capable than the coarse chunks, not less.
- Cost: verse granularity produces far more vectors (thousands vs. ~1,600 for the
  DRB; the earlier 150-word experiment already hit 7,663). This pushes scale onto
  the vector store — see [ADR-005](adr-005-vector-store-chroma-and-lexical-store-path.md).
- The window size must be wide enough to span the interpretant scatter; too narrow
  (one segment) reintroduces the "kills correlation" problem. Hence it is a knob.

## Alternatives considered

- **Fixed word-count chunks (status quo).** Rejected: boundary bleed, one coarse
  label per chunk, and empirically worse target ranks as shown above.
- **Chapter-level segments.** Rejected: too coarse to locate the convergence
  precisely, and still cannot form regions that cross the chapter boundary where
  the Abraham signals actually sit.
- **Topic/semantic segmentation** (infer region boundaries from content shifts).
  Rejected as a non-goal: regions are defined structurally and by window size, not
  by inferred topic — deterministic and auditable beats learned boundaries here.
