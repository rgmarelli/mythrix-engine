# ADR-017 — A `"filter"`-directive match requires convergence; `"exact"` does not

- **Status**: Accepted
- **Date**: 2026-07-29
- **Narrows**: [ADR-004](adr-004-absolute-floor-and-lexical-specificity-ranking.md)'s "an isolated match is a first-class, rankable result" principle, and [ADR-013](adr-013-region-rollup-sole-query-shape.md)'s restatement of it as kind-independent, for the `"filter"` directive only.
- **Realized by**: [retrieval.md](../retrieval/retrieval.md) FR-RT-20; [ranking.md](../retrieval/ranking.md) FR-RK-03.

## Context

Before ADR-013, a `"filter"`-directive token had a second role beyond
literal-text matching (the retired FR-RT-09): it was a first-class member of
a concept-pair result, so a match reached only through a filter token always
surfaced *paired* with a converging concept ("child + 100"). ADR-013 retired
that pair aggregator — region rollup is now the only result shape — and
restated the filter directive's matching semantics as membership-only,
kind-agnostic eligibility (FR-RT-20): a region matched by a single
interpretant is eligible regardless of whether that interpretant is
`"concept"`, `"exact"`, or `"filter"`.

That restatement erased the distinction that gave `"filter"` its previous
guarantee. In practice, a segment containing a filter token with no
converging concept nearby now surfaces as an ordinary, unpaired
single-interpretant region — indistinguishable from any other legitimately
isolated match. There is no signal left that this was a token whose value
was only ever meant to be read together with something else.

`"exact"` does not have this problem: FR-RT-17 establishes its standalone
eligibility deliberately — every literal occurrence of an exact-directive
token is supposed to surface, whether or not anything else matches nearby.
The two directives were never equivalent in intent; ADR-013 collapsed them
into the same eligibility rule because both are membership-only matches with
no similarity score, not because they were meant to behave identically.

## Decision

A region's eligibility is amended for `"filter"`-kind matches specifically:

- A region whose matches are exclusively `kind == "filter"` — no
  `"concept"` match and no `"exact"` match within it — is not eligible,
  regardless of `region_min_interpretants` and regardless of how many
  distinct filter tokens matched.
- A region with at least one `"concept"` or `"exact"` match remains eligible
  under the existing count-based rule (FR-RK-03), and any `"filter"` matches
  it also contains continue to contribute to convergence count and score
  exactly as before.
- `"exact"`-directive matches are unaffected: they remain eligible in
  isolation per FR-RT-17.

## Consequences

- `"filter"` returns to being purely a co-occurrence booster: it can only
  ever raise the score or convergence count of a region some other match
  already made eligible. A corpus segment containing a filter token with
  nothing else nearby produces no region — the same practical outcome the
  retired pair aggregator gave by only ever displaying `"filter"` alongside a
  concept, now enforced at the region-eligibility layer instead of a display
  layer.
- Matching, clustering, and scoring are untouched: `_search_deep_pools`,
  `build_query_texts`, `_collect_filter_tokens`, and the region score formula
  (FR-RK-05) behave exactly as ADR-013 left them. Only the final eligibility
  check changes.
- The two literal-containment directives (`"filter"`, `"exact"`) no longer
  share one eligibility sentence in the spec; each states its own rule
  (FR-RT-20 for the carve-out, FR-RT-17 for `"exact"`'s independence).

## Alternatives considered

- **Documentation only** (treat the isolated filter hit as expected,
  unproblematic behavior). Rejected: the directive's authored intent — a
  narrowing filter combined with a concept, never a bare hit — would remain
  unenforced, and every curator-authored `"filter"` token would keep
  surfacing results indistinguishable from a design defect.
- **Add an additive "convergence kind" field instead of an eligibility
  change** (keep every isolated match eligible per FR-RT-20 as it stood, but
  let a consumer tell a filter-only region apart from a converged one).
  Rejected: it leaves the ineligible case reachable and pushes the
  distinction onto every consumer to interpret and filter client-side,
  rather than enforcing it once, in the pipeline, where the rest of region
  eligibility already lives.
