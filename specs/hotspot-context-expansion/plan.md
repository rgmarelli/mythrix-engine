# Hotspot Context Expansion — Plan

## Overview

Add an **Add Context** control to `HotspotDetailPanel` that progressively loads
surrounding verbatim segments of the hotspot's source and interleaves them, in
ordinal order, with the hotspot's matched segments. The AI-summary action then
covers the whole loaded set. The only new backend capability is a
coordinate-based segment lookup — fetching a contiguous ordinal range of one
source from the vector store, no similarity search involved. All chapter-bound,
gap-fill, and edge-stepping logic lives in the frontend; the backend stays a
dumb range fetch (spec FR12).

The chapter/section signal already exists end-to-end in storage: every chunk is
ingested with `ordinal` and `section` metadata (`vector/store.py`
`add_chunks`), and `VectorHit`/`Chunk` already carry both. The one gap is that
`core.models.Segment` (and therefore the region wire shape the UI consumes)
drops `section`, so the client can't currently tell which chapter a matched
segment belongs to. We thread `section` through.

## Data flow

```
Add Context click
  → client computes: internal gaps? / which edges can still extend?
  → GET /api/segments?source_id&start_ordinal&end_ordinal   (small range)
  → query_service.fetch_source_segments
      → graph_store.get_source(source_id)      (existence → 404)
      → vector_store.get_segments(...)          (Chroma .get by ordinal range)
      → map Chunk → core.Segment (now with section)
  → list[Segment] JSON
  → client merges into panel state, marks context vs matched, updates edge bounds
```

## Backend changes

### 1. `core.models.Segment` gains `section`

Add `section: str = ""` to `Segment`. Populate it where regions are built
(`retrieval/pipeline.py:479`): `Segment(ordinal=ordinal, locator=hit.locator,
text=hit.text, section=hit.section)` — `hit` is a `VectorHit`, which already
carries `section`. Additive and default-safe: every existing `Segment(...)`
call site stays valid, and the region wire shape simply gains one field.

### 2. `ChromaVectorStore.get_segments`

```python
def get_segments(self, source_id: str, *, start_ordinal: int, end_ordinal: int) -> list[Chunk]:
```

- Returns every chunk of `source_id` whose `ordinal` is in
  `[start_ordinal, end_ordinal]`, reconstructed as `Chunk` and **sorted by
  ordinal ascending** (Chroma `.get` does not guarantee order).
- Uses `self._collection.get(where=..., include=["documents", "metadatas"])`
  with
  `{"$and": [{"source_id": {"$eq": source_id}}, {"ordinal": {"$gte": start}}, {"ordinal": {"$lte": end}}]}`.
- `start_ordinal > end_ordinal` returns `[]` without querying.
- Reuses the same metadata fields `similarity_search` already reads
  (`chunk_index`, `char_start`, `char_end`, `locator`, `ordinal`, `section`),
  so the reconstruction mirrors the existing `VectorHit` hydration.

Returning `Chunk` (the vector module's own currency) rather than `VectorHit`
keeps this off the search path — `VectorHit.distance` has no meaning for a
coordinate lookup.

### 3. `query_service.fetch_source_segments`

New function alongside `query_regions`, the shared home for retrieval
orchestration:

```python
def fetch_source_segments(*, source_id, start_ordinal, end_ordinal,
                          graph_store, vector_store) -> tuple[Segment, ...]:
    graph_store.get_source(source_id)          # raises SourceNotFoundError → 404
    chunks = vector_store.get_segments(source_id,
                                       start_ordinal=start_ordinal,
                                       end_ordinal=end_ordinal)
    return tuple(Segment(ordinal=c.ordinal, locator=c.locator,
                         text=c.text, section=c.section) for c in chunks)
```

Validating existence through `graph_store.get_source` gives a real 404 for an
unknown source rather than a silent empty list, matching how every other route
surfaces a missing entity.

### 4. Route `GET /api/segments`

```python
@router.get("/segments", response_model=list[Segment])
def source_segments(source_id: str, start_ordinal: int, end_ordinal: int,
                    stores: Stores = Depends(get_stores)) -> list[Segment]:
```

Thin: delegates to `fetch_source_segments`. Docstring notes it is a
coordinate lookup (no generation, no similarity) feeding the web UI's Add
Context action, distinct from `/api/query`.

### 5. `api/errors.py`: 404 for unknown source

Add `SourceNotFoundError` to the `_NOT_FOUND` tuple so the new route returns
404 (it is currently absent — only sign/tradition/manifestation map to 404).

## Frontend changes

### Types (`api/types.ts`)

- Add `section: string` to `RegionSegment` and `HotspotSegment`.
- The `/api/segments` payload is `Segment[]` — same shape as `RegionSegment`
  (`ordinal`, `locator`, `text`, `section`), all snake-free, so it maps
  straight onto `HotspotSegment` with no camel-case translation.

### Client (`api/client.ts`)

- `toHotspot` passes `section` through in the `segments` map.
- New `fetchSegments(sourceId, startOrdinal, endOrdinal): Promise<HotspotSegment[]>`
  hitting `GET /api/segments`, mirroring the existing error handling (reads
  `detail`, throws `Error`).

### `HotspotDetailPanel` state machine

Local state (resets automatically per hotspot — the panel is already keyed by
`regionId` in `App.tsx:189`, satisfying FR10):

- `segments: HotspotSegment[]` — initialized from `hotspot.segments`, kept
  sorted by ordinal; context loads merge in (dedupe by ordinal).
- `matchedOrdinals: Set<number>` — the original matched ordinals, for render
  classing and to protect them during merge.
- `leadingBounded`, `trailingBounded: boolean` — set once an edge probe reveals
  a chapter boundary or a source end.
- `isAddingContext: boolean`, `contextError: string | null`.

**`handleAddContext` algorithm:**

1. Sort loaded ordinals → `minO`, `maxO`. Compute unfilled internal gaps =
   ordinals in `(minO, maxO)` absent from the loaded set.
2. **If gaps remain:** `fetchSegments(sourceId, minO, maxO)`, merge all returned
   segments (existing matched ones keep their flag). One request fills every
   internal gap (FR2). Done.
3. **Else extend edges (FR3):** in parallel, for each edge not yet bounded:
   - Leading: `fetchSegments(sourceId, minO - 1, minO - 1)`.
     - Empty → `leadingBounded = true` (source end, FR5).
     - Segment `s` returned: let `edgeSection` = section of the current `minO`
       segment. If `edgeSection !== "" && s.section !== edgeSection` →
       `leadingBounded = true`, discard `s` (chapter boundary, FR4). Else merge
       `s`.
   - Trailing: symmetric with `maxO + 1` and the `maxO` segment's section.

**Button enabled** iff any unfilled internal gap exists, or `!leadingBounded`,
or `!trailingBounded` (FR6/FR7). Disabled state shows a "full context loaded"
affordance.

**Render:** map the sorted `segments`; a segment gets class `context` when its
ordinal ∉ `matchedOrdinals`, else the existing matched/active classing.
Interpretant chips still target matched ordinals via `segmentElementId`
(unchanged) — context segments are never chip targets (FR11).

**AI summary (FR8):** build `passageText` from the full sorted `segments` (not
just `hotspot.segments`); the concept list stays `hotspot.matches` mapped to
interpretant values.

**Errors (FR13):** a failed context load sets `contextError` only — it never
touches `segments`, the hotspot, or the query result.

### Styling (`index.css`)

- `.add-context-button` (mirrors `.ai-summary-button`).
- `.segment.context` — visually subordinate to matched segments (e.g. muted /
  reduced emphasis) so matches stay the focus.

## Chapter boundary — why per-edge section comparison works

`section` is `""` for a source with no declared structure, the chapter locator
otherwise (scripture: e.g. `"Genesis 20"`; Bahir: the section number). Comparing
a probed neighbor's `section` against the current edge segment's `section`:
- both non-empty and equal → same chapter, absorb;
- non-empty and different → chapter boundary, stop that edge (FR4);
- edge section `""` → no chapters; the only stop is an empty probe = source end
  (FR5).

A hotspot spanning two chapters stops each edge at *its own* edge segment's
chapter, which is the graceful multi-chapter reading agreed in the spec.

## Edge cases

- Hotspot already internally contiguous (no gaps): first click extends edges
  directly — no wasted click.
- Single-segment hotspot: `minO == maxO`, no gaps; clicks extend both edges.
- Source end reached on one edge, chapter room on the other: only the open edge
  advances; button stays enabled until both are bounded (FR6).
- A probe that returns a segment already loaded (shouldn't happen with ±1, but
  defensive): merge dedupes by ordinal — idempotent.

## Testing

- `tests/unit` vector store: `get_segments` returns the right ordinal-sorted
  slice; out-of-range and `start > end` return `[]`; respects `source_id`.
- `query_service.fetch_source_segments`: maps `Chunk → Segment` with `section`;
  unknown `source_id` raises `SourceNotFoundError`.
- API route test: `GET /api/segments` happy path shape; 404 for unknown source.
- Region/segment serialization test updated for the new `section` field.
- Frontend: existing web test setup (if any) — otherwise manual verification via
  `/run` against the Genesis corpus (chapter-bounded) and the Bahir
  (numbered-section) plus a paragraph-only source (unbounded to source ends).

## ADR

No ADR warranted. This adds a read-only, coordinate-based access path to the
existing vector store and a UI affordance — local, reversible, and within the
existing web-viewer/API architecture (master FR49). It introduces no new system
boundary, storage, or data-flow decision of lasting architectural weight. (ADR
0005 already records the vector-store choice; this rides on it.)

## Risks / trade-offs

- **Chatty edge stepping.** ±1-per-click means one round trip per click per open
  edge. Acceptable for a local single-user dev tool; the requests are tiny
  coordinate lookups. If it grates in use, the step size is a single constant to
  raise — no protocol change.
- **`section` string identity.** Chapter equality is exact string comparison on
  the ingest-time `section` locator. This is exactly the value the segmenter
  wrote, so it is stable; but it does mean two genuinely different chapters must
  never share a `section` string (they don't — scripture carries the book name,
  Bahir the section number).
- **No server-side span cap.** The client only ever requests small ranges, so we
  don't add a cap; a future non-UI caller wanting large ranges should revisit.
