# ADR-021 — Locator normalization at query time, not ingest time

- **Status**: Accepted
- **Date**: 2026-07-31
- **Extends**: [ADR-020](adr-020-source-declared-chapter-heading-patterns.md)
- **Realized by**: [specs/retrieval/corpus.md](../retrieval/corpus.md) FR-CO-12, FR-CO-16–FR-CO-18

## Context

`chapter_section`'s four staged sources (ADR-020) each transcribe their chapter/subsection headings with a different, inconsistent casing convention — one source's chapter titles come through as already-mixed-case, its subsection titles as ALL CAPS, within the same book. Before this decision, `_segment_chapter_section` flattened a segment's display `locator` directly from the source's own matched heading text at ingest time: `"{chapter heading} › {subsection heading}"`, verbatim casing and all. Two problems followed from baking that string in at ingest:

- The casing inconsistency leaked straight into the UI and into whatever an agent/LLM tool call retrieved, with no way to fix it short of a full reingest of the affected source.
- A region spanning more than one subsection had no clean way to build a proper merged citation (e.g. "sections 19 and 20"): by the time the region-rollup path ran, the structural pieces it would need — which chapter, which subsection, which running numbers — were already gone, collapsed into one opaque string. The existing `region_locator` could only crudely concatenate two already-flattened locators.

A related, narrower version of the same problem existed for `numbered_section` (the Bahir): a multi-segment region produced `"§83–§90"` by concatenating two already-correct single-point locators, instead of the proper grouped form `"§§83–90"`.

## Decision

A `chapter_section` chunk/segment stores the raw structural pieces it belongs to — chapter ordinal and title, subsection ordinal and title — extracted verbatim from the source's own matched heading text (optionally isolated via a `title` named capture group in the same source-declared pattern ADR-020 established, extending that mechanism to title extraction, not just boundary detection). The chunk's own `locator` field stays empty at this scheme; the final, human-readable display string — Title Case (via the `titlecase` package, not a hand-rolled algorithm), `"Chapter N"`/`"Section N"` abbreviated to `"Ch. N"`/`"§N"`, and multi-subsection/multi-chapter regions merged into a grouped range (`"§§19–20"`, `"Chs. 6–7"`) — is built by one shared module (`locator_format.py`), called from exactly the handful of places a `Segment` is constructed from a stored chunk.

Because that module is the single point where a `Segment.locator` gets its final value, every reader of a retrieved `Segment` sees the identical formatted string with no separate formatting step to duplicate or drift out of sync: the web viewer's region panel and reading-panel breadcrumb, and the agent/LLM tools (`fetch_segments`, `query_sign`) alike. The same query-time-merge principle extends to `numbered_section`'s grouped-range fix (`"§83"` + `"§90"` → `"§§83–90"`), even though that scheme's chunks needed no ingest-time field changes — only `region_locator`'s merge logic changed.

`scripture_verse` (the Bible) is untouched: its verse-numbered locator format has no casing-consistency problem and no grouped-range gap to close.

## Consequences

- Fixing a casing convention, an abbreviation rule, or a range-merge bug is a code change alone — it applies retroactively to already-ingested content on the next query, never requiring a reingest to take effect for a display-only fix.
- A `chapter_section` chunk carries four additional stored fields (`chapter_ordinal`, `chapter_title`, `subsection_ordinal`, `subsection_title`), propagated through `Chunk`, Chroma chunk metadata, `VectorHit`, and `Segment` — every one of these types grows by four fields, all defaulted to `0`/`""` and harmless for every other scheme.
- New dependency: `titlecase`.
- Zero frontend changes: the web viewer already treated `locator` as one opaque, already-formatted string; only its *content* changes, never its shape or how any component consumes it.
- Cost: a new invariant to maintain across the codebase — every future construction site of a `chapter_section`/`numbered_section` `Segment` must route through the shared formatting module rather than reading a chunk's raw fields directly, or the single-formatting-point guarantee silently breaks for that one path.

## Alternatives considered

- **Keep flattening `locator` at ingest, but normalize casing/abbreviation at ingest time too.** Rejected: still requires a full reingest to fix a formatting bug or add a new abbreviation rule, and still cannot solve the multi-subsection range-merge problem, since the structural pieces needed to build a proper merged range are exactly what flattening at ingest discards.
- **Format client-side in the web viewer, from raw structural fields sent over the wire.** Rejected: would require exposing the four raw fields to the frontend and reimplementing the same Title Case/abbreviation/range-merge logic there, duplicated against whatever the agent/LLM tool path does server-side — the two would inevitably drift, defeating the one guarantee this decision exists to provide (a retrieved segment reads identically wherever it's consumed).
- **Hand-rolled Title Case implementation.** Rejected in favor of the `titlecase` package — headline-style title-casing (minor-word rules, first/last-word-always-capped) is a solved, general problem not worth re-deriving.
