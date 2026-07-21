# ADR 0004 — Absolute match floor + lexical specificity ranking; isolated matches first-class

- **Status**: Accepted
- **Date**: 2026-07-21
- **Realized by**: `specs/symbol-interpretation-core/spec.md` FR36, FR41–FR44

## Context

Three ranking problems surfaced, each with a decisive test.

**1. Summing raw per-interpretant scores over-rewards long, list-like passages.**
A census or genealogy chapter carries a weak trace of *everything*, so a naive
`sum` of interpretant scores floated such chapters above genuinely specific
convergences.

**2. Specificity weighting must come from *lexical* rarity, not dense scores.**
Down-weighting ubiquitous interpretants and up-weighting rare ones (IDF) is the
fix for #1 — but computing the "rarity" from normalized *dense* score
distributions backfired: dense similarity is diffuse, and it labelled the rare word
`laughter` as the *most common* interpretant. Computing document frequency from
**literal surface-form presence** instead (`laughter` in 11 chapters → weight 4.67;
`hundred` in 260 → 1.51) put the Genesis target at **rank 1**, collapsing the
census noise.

**3. Min-max normalizing match strength fabricates matches.** This was the sharpest
finding, from the Sefer HaBahir. Qoph's and Nun's symbolic interpretants
(`monkey`, `laughter`, `Fish`, `Pisces`, `Scorpio`) simply do not occur in the
Bahir — their raw cosine sits at **noise level (~0.44–0.50; corpus mean ~0.38)**.
Min-max normalizing *within the query* stretched that noise band to a confident
`1.00`, and the summed score then flagged **174 of 200 Bahir sections** as a Nun
"convergence", topping out on a section about the letter *Mem*. For contrast, a
query the Bahir genuinely contains scores far higher: `"Torah wisdom"` → 0.706,
`"blessing and the letter Bet"` → 0.711.

**4. Convergence must not be an eligibility gate.** An early version required ≥2
distinct interpretants to rank a region. That **suppressed the correct answer**:
the Bahir's §83 is literally *"And what is Nun?"* — the definitional section for
the letter — matched by `Nun` alone at raw **0.762**, the single strongest match in
the whole experiment. An isolated but strong match is a valid, valuable result.

## Decision

- **Absolute match floor.** A concept interpretant matches a segment only if its
  **raw** similarity clears an absolute threshold (≈0.50). The floor is evaluated
  on the raw cosine — never a rank cutoff, never a within-query normalized value —
  so a corpus that lacks a concept yields *no* match for it rather than a
  best-of-noise match. Exact tokens are containment guarantees and are not floored.
- **Raw floored strength enters the score**, not a normalized value, so absolute
  match quality is preserved and comparable across queries and corpora.
- **Specificity weight = IDF from literal surface-form document frequency**
  (`log(units / units_containing_the_surface_form)`), never from dense-score
  distributions.
- **Region score = Σ over matching interpretants of (specificity_weight × best
  floored strength).** Convergence raises rank as an *emergent* property of the sum
  (more real interpretants → higher score), **not** through a gate.
- **Isolated matches are first-class.** Minimum distinct interpretants defaults to
  **1**. A single interpretant clearing the floor produces a rankable region.

## Consequences

- The engine can honestly return **"nothing here"** — Qoph over the Bahir correctly
  yields almost nothing, instead of a fabricated ranking.
- With the floor, Nun over the Bahir returns **§83 as the top isolated hit** and
  §131 (`kingdom` + `Nun`) as the one true 2-way convergence — matching intent.
- Ranking rewards *rare + strong + multiple* without ever hiding *rare + strong +
  alone*.
- The floor value and the min-interpretants count are tunable knobs; the floor is
  embedding-model-specific and must be revisited if the embedder changes.
- Requires cheap document-frequency counts at scale — a lexical/statistics
  capability the storage layer must provide
  ([ADR 0005](0005-vector-store-chroma-and-lexical-store-path.md)).

## Alternatives considered

- **Min-max normalized match strength.** Rejected: fabricates matches on corpora
  lacking the interpretant (174/200 false convergences).
- **Dense-score-derived IDF.** Rejected: diffuse; mislabels rare terms as common.
- **Unweighted sum of scores.** Rejected: over-rewards list-like passages.
- **Convergence (≥2) as an eligibility gate.** Rejected: suppresses correct
  isolated matches such as Nun §83.
