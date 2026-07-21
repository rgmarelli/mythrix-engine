# Query Viewer Facet/Fragment Redesign — Spec

## Problem

The current query-viewer UI (`specs/query-viewer-web-ui/`) organizes results into a "Graph facts" box, one passage-card grid per interpretant, and one passage-card grid per interpretant-pair convergence. It has no faceted filtering, no single ranked view of results, and its convergence detection is limited to pairs of interpretants.

## Goals

- Replace passage-grouping-by-interpretant with a single ranked list of fragments (passages), each carrying its true count of distinct converging interpretants, for any number of interpretants, not just pairs.
- Add two independent, AND-combined facets (Sources, Interpretants) that filter the fragment list.
- Rename "concept" to "Interpretant" throughout the UI.
- Keep a per-fragment detail panel with full text, citation, and an on-demand AI summary.

## Non-goals

- Multi-select within a single facet row (single-select per row, decided).
- A visual "notable hotspot" threshold/styling tier.
- Any change to the retrieval/scoring algorithm itself (RRF, concept-scoping, exact-value filtering) — only what is aggregated and returned changes.
- Any change to `/api/traditions`, `/api/symbols`, `/api/summarize`, or the CLI's `mythrix query` output.

## Terminology

- **Interpretant**: the UI-facing term for what the backend previously exposed as a "concept" — an atomic interpretant value used to build a retrieval query.
- **Fragment**: a single retrieved passage/chunk from a source document.
- **Convergence**: the number of distinct Interpretants matched *semantically* within the same fragment (FR3).
- **Exact-value match**: a fragment/Interpretant match produced by a literal-text filter (an Interpretant carrying a `query.directive: "filter"` annotation) rather than a similarity score. Reported like any other match (FR2) but excluded from convergence (FR3).
- **Property** nodes are not shown to the user anywhere in this UI.

## Functional requirements

### Results data

- FR1: A query result is a single ranked list of fragments; no fragment appears more than once in that list.
- FR2: Each fragment reports every distinct Interpretant that matched it and that Interpretant's score, not only the Interpretant(s) that caused it to be included in the result. This includes exact-value matches (score `0`).
- FR3: A fragment's convergence count is the number of distinct Interpretants recorded on it (FR2) whose match is semantic (excludes exact-value matches), independent of which facet filter, if any, is currently applied.
- FR4: Fragments are ranked by convergence count (descending), ties broken by score.
- FR5: A query result includes facet data: one entry per Source with a count of fragments from that source, and one entry per Interpretant with a count of fragments it matched.

### Facets

- FR6: A Sources facet offers "All sources" plus one chip per corpus source; default "All sources".
- FR7: An Interpretants facet offers "All" plus one chip per distinct Interpretant found for the current query, each labeled with its total match count; default "All".
- FR8: Each facet row is single-select.
- FR9: Selecting a Source and an Interpretant filters the fragment list to fragments that satisfy both.
- FR10: Selecting a specific Interpretant with "All sources" filters to that Interpretant across every source.
- FR11: Selecting a specific Source with "All" Interpretants filters to every fragment from that source.

### Hotspot list

- FR12: A left-column list shows the current filtered, ranked fragment list.
- FR13: The list's header text reflects the active filters: no filters, an Interpretant filter alone, or a Source and Interpretant filter together.
- FR14: Each list item shows a fragment title, its true convergence badge (FR3), and a subtitle listing which Interpretants matched.
- FR15: The active/selected list item is visually distinguished from the rest.

### Fragment detail panel

- FR16: A right-column panel shows the selected fragment's source breadcrumb, title, and convergence badge.
- FR17: The panel shows one chip per Interpretant that matched the fragment, each with its individual score.
- FR18: The Interpretant(s) matching the current active filter are visually distinguished from Interpretant(s) that matched the fragment but are outside the current filter; none are hidden.
- FR19: The panel's fragment text is rendered with no highlighting of matched spans.
- FR20: A "Generate AI summary" action requests a summary of the selected fragment's text, scoped to the fragment's matched Interpretant(s), rendered in a visually distinct box below the fragment text. It is not triggered automatically on selection.
- FR21: The panel provides navigation to the previous/next fragment within the current filtered, ranked list, and an action to copy the fragment's citation/reference string.

### Query tuning

- FR22: The query form offers an optional minimum-score input, applied to the next query submission only. Left blank, no override is sent and the server's own default governs.

### Removed from this design

- The "Graph facts" box.
- Per-interpretant and per-pair passage-card grids.
- Text-highlighting of matched Interpretant spans inside fragment text.
