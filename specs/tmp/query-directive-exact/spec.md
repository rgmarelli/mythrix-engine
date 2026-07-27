# Spec: `exact` query directive

## Problem

Two `query.directive` values exist today: `"filter"` and `"skip"`. A `"filter"`-directive interpretant is excluded from the plain concept query and only ever contributes a literal-text filter paired with every other concept in the sign. There is no directive for the case where a curator wants an interpretant's value to be searched *exclusively* through its own literal-text filter, scoped to itself, so every hit is a guaranteed verbatim occurrence rather than a plain semantic guess — useful for values (e.g. numbers) where a plain semantic query alone is not a reliable enough signal.

Separately, the UI currently labels a `"filter"`-directive hit as `"exact"` (`Match.kind == "exact"`). That label is needed for the new directive instead.

## Goals

- Add `"exact"` as a recognized `query.directive` value.
- An `"exact"`-directive interpretant's value is searched exclusively through a literal-text-filtered query — never through an unrestricted plain query — so every hit found under its value is a guaranteed literal match.
- An `"exact"`-directive interpretant's literal-text filter is scoped to its own concept's query only — it is never cross-joined with unrelated concepts as a pair candidate.
- `as_token` is optional for `"exact"`: when omitted, the literal filter searches the interpretant's own `value`.
- A hit reached through an `"exact"`-directive interpretant is surfaced to API/UI consumers as `Match.kind == "exact"`.
- A hit reached through a `"filter"`-directive interpretant is surfaced as `Match.kind == "filter"` (changed from `"exact"`).

## Non-goals

- No change to `"filter"`'s or `"skip"`'s existing retrieval behavior — only their UI-facing label changes, for `"filter"`.
- No change to how `"filter"` tokens are collected or cross-joined with other concepts (FR-RT-09) — that remains global, `"filter"`-only.
- No enforcement/validation added for `directive` values — it remains free text, as today.

## Functional Requirements

- FR-EX-01: An interpretant carrying `query.directive: "exact"` contributes no unrestricted plain query of its own value — unlike an ordinary concept, it is searched only through the literal-filtered query of FR-EX-02.
- FR-EX-02: An interpretant carrying `query.directive: "exact"` contributes a literal-text-filtered query of its own value, using `query.as_token` if given, otherwise its own `value`. This is the interpretant's sole query, and stands in as its "concept" for display, scoring, and pair-candidate purposes.
- FR-EX-03: A literal-text filter contributed by an `"exact"`-directive interpretant is not cross-joined with other concepts as a pair candidate — unlike a `"filter"`-directive token (FR-RT-09), which is.
- FR-EX-04: A retrieval hit reached through an `"exact"`-directive interpretant's literal filter is reported with `Match.kind == "exact"`.
- FR-EX-05: A retrieval hit reached through a `"filter"`-directive interpretant's literal filter is reported with `Match.kind == "filter"` (previously `"exact"`).
- FR-EX-06: Within one region, an `"exact"`-directive interpretant that has both a `"concept"` match and its own literal-filter match for the same value is reported once, not twice — the `"concept"` match is kept and the literal-filter match is dropped as redundant. The literal-filter match is reported on its own only when no `"concept"` match for that value survives elsewhere in the region.
