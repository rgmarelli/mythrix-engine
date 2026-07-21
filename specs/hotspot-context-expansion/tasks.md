# Hotspot Context Expansion — Tasks

Ordered so each backend layer is testable before the frontend consumes it.
Backend first (T1–T7), then frontend (T8–T14), then verification (T15–T16).

## Backend

- [x] **T1 — Add `section` to `core.models.Segment`.**
  Add `section: str = ""` to `Segment`. No other model changes.

- [x] **T2 — Populate `section` in region rollup.**
  In `retrieval/pipeline.py` (region-building loop, ~L479), pass
  `section=hit.section` into `Segment(...)`. Confirm no other `Segment(...)`
  construction site needs updating.

- [x] **T3 — `ChromaVectorStore.get_segments`.**
  Add `get_segments(source_id, *, start_ordinal, end_ordinal) -> list[Chunk]`:
  Chroma `.get` with the `$and` source_id + ordinal-range `where`, reconstruct
  `Chunk`s from metadata, sort by ordinal ascending; `start > end` returns `[]`.

- [x] **T4 — `query_service.fetch_source_segments`.**
  New function: validate via `graph_store.get_source(source_id)`, call
  `vector_store.get_segments`, map `Chunk → Segment` (with `section`), return a
  tuple.

- [x] **T5 — Route `GET /api/segments`.**
  Add to `api/routes.py`, `response_model=list[Segment]`, delegating to
  `fetch_source_segments`; docstring clarifies it as a non-generation,
  non-similarity coordinate lookup for the Add Context action.

- [x] **T6 — 404 for unknown source.**
  Add `SourceNotFoundError` to `_NOT_FOUND` in `api/errors.py`.

- [x] **T7 — Backend tests.**
  - `get_segments`: correct ordinal-sorted slice; out-of-range → `[]`;
    `start > end` → `[]`; other sources excluded.
  - `fetch_source_segments`: `Chunk → Segment` mapping incl. `section`; unknown
    source raises `SourceNotFoundError`.
  - Route: `/api/segments` happy-path shape; 404 on unknown source.
  - Update any region/segment serialization test/fixture for the new `section`
    field.

## Frontend

- [x] **T8 — Types.**
  Add `section: string` to `RegionSegment` and `HotspotSegment` in
  `api/types.ts`.

- [x] **T9 — Client.**
  `toHotspot`: thread `section` through the segment map. Add
  `fetchSegments(sourceId, startOrdinal, endOrdinal)` in `api/client.ts` with
  the existing `detail`-reading error handling.

- [x] **T10 — Panel state.**
  In `HotspotDetailPanel`, add state: `segments` (init from `hotspot.segments`,
  sorted), `matchedOrdinals` (Set from the initial segments), `leadingBounded`,
  `trailingBounded`, `isAddingContext`, `contextError`.

- [x] **T11 — `handleAddContext`.**
  Implement the algorithm from plan.md: gap-fill first (`fetchSegments(min,max)`),
  else parallel ±1 edge probes with per-edge chapter/source-end bounding; merge
  results (dedupe by ordinal); set bound flags; manage
  `isAddingContext`/`contextError`.

- [x] **T12 — Add Context button + render.**
  Render the button (disabled when no gap remains and both edges bounded, with a
  "full context loaded" state). Render `segments` sorted; class ordinals not in
  `matchedOrdinals` as `context`. Keep interpretant chips anchoring to matched
  ordinals. Surface `contextError` without clearing the hotspot.

- [x] **T13 — AI summary over loaded context.**
  Change `handleSummarize` to build `passageText` from all loaded `segments`
  (sorted); keep concepts = `hotspot.matches` interpretants.

- [x] **T14 — Styling.**
  `.add-context-button` and `.segment.context` in `index.css`.

## Verification

- [x] **T15 — Lint/format/tests.**
  `ruff check .`, `ruff format .`, run the Python test suite; `oxlint` / web
  build for the frontend.

- [x] **T16 — End-to-end manual check (`/run`).**
  Verified live against the ingested dataset (`.mythrix/`) via `uvicorn` +
  the Vite dev server, driven through the browser:
  - Scripture (`en_drb`, John 3): gap-fill (John 3:9) in one click; ±1
    stepping both edges; leading edge correctly stopped at John 3:1 and did
    not leak John 2:25 (different `section`) on repeated clicks; AI summary
    after expansion covered the full loaded John 3:1–3:19ish span, not just
    the two originally-matched verses.
  - Bahir (`en_bahir`, numbered_section): multi-segment gap (§186–§187)
    filled in one range fetch; edges immediately bounded after the gap-fill
    and the button read "Full context loaded" — correct per spec's
    definition of a numbered section as its own chapter (spec.md vocabulary:
    "chapter boundary ... e.g. a scripture chapter or a numbered section").
  - No paragraph-only (unstructured) source exists in the current ingested
    dataset to exercise FR5's fully-unbounded case; the gap-fill and edge-probe
    code path is scheme-agnostic (only branches on `section === ''`), so this
    is covered by the same logic already verified above, not a separate
    untested path.
