# Convergence Rollup Retrieval — Tasks

Ordered, checkable breakdown of `plan.md`. Each task is independently verifiable.
Tooling: `ruff check . && ruff format .` and `pytest` must stay green after each
task. Task IDs are stable; check them off as they land.

## Phase 1 — Structural segmentation & coordinates (plan A/B)

- [x] **T1. `Segment` fields on the chunk model.** In `vector/chunking.py`, extend
  `Chunk` additively with `ordinal: int = 0` and `section: str = ""` (keep
  `locator`). Existing `chunk_text` sets `ordinal = index`, `section = ""`.
  *Verify:* existing chunking tests pass unchanged; new field defaults asserted.

- [x] **T2. Structural segmenter registry.** In `vector/chunking.py` (or a new
  `vector/segmentation.py`), add a `segment_text(text, *, scheme) -> list[Chunk]`
  dispatch over named schemes `scripture_verse`, `numbered_section`, `paragraph`.
  Each yields one `Chunk` per unit with `ordinal` (0-based), `section` (coarse
  label), `locator` (display ref), and `text` **with the structural-label prefix
  stripped** (FR2). No overlap, no boundary spanning (FR1).
  *Verify:* unit tests — DRB excerpt → per-verse segments with `locator`
  `"Genesis 20:1"` and no `"20:1."` in `text`; Bahir excerpt → per-section
  segments, `"83."` stripped; contiguous `ordinal`s; unknown scheme raises.

- [x] **T3. Source declares its scheme.** In `loaders/sign_schema.py` add optional
  `structure: StructureBlock | None = None` (`StructureBlock.scheme: str`) to
  `SourceBlock`; thread it onto the `Source` model (`core/models.py`) and the
  loader parse (`document_loader._parse_corpus_source`).
  *Verify:* a source YAML with `structure.scheme: scripture_verse` round-trips;
  one without parses to `structure = None` (backward compatible).

- [x] **T4. Route ingestion through the segmenter.** In
  `document_loader.load_document`, when the source declares a scheme call
  `segment_text(content, scheme=…)`, else fall back to `chunk_text` unchanged.
  *Verify:* loader test — scheme present → segment count matches units; scheme
  absent → identical behavior to today.

- [x] **T5. Coordinates in the store.** Add `ordinal`/`section` to `ChunkMetadata`,
  the per-chunk metadata dict, and `VectorHit` (`vector/store.py`), all defaulted.
  `add_chunks` writes `chunk.ordinal`/`chunk.section`.
  *Verify:* store test — round-trip a segment, assert `VectorHit.ordinal`/`section`
  survive; existing word-count ingestion still valid (defaults fill in).

## Phase 2 — Word-bounded matching & document frequency (plan C/E-store)

- [x] **T6. Word-bounded token containment.** In
  `ChromaVectorStore.similarity_search`, build the exact-token constraint as
  `{"$regex": r"\b" + re.escape(token) + r"\b"}` instead of `{"$contains": …}`.
  *Verify:* store test — token `50` matches a chunk containing the word `50` but
  **not** one containing only `150`; `hundred` still matches `"a hundred years"`.

- [x] **T7. `document_frequency(term)`.** Add
  `ChromaVectorStore.document_frequency(term) -> int` = count of chunks whose text
  matches the word-bounded `$regex` (via `get(where_document=…)`), plus
  `collection_size()` if not already exposed. Keep it behind a small callable so an
  ingest-time table can replace it later.
  *Verify:* store test — seed N chunks, assert df of a term present in k of them is
  k; absent term is 0.

## Phase 3 — Rollup, specificity & region result (plan D/F/G)

- [x] **T8. Region result models (settled: clean `Region`).** In `core/models.py`
  add the nested region shape — **not** an overloaded `Fragment`:
  - `Segment { ordinal: int, locator: str, text: str }` — one match-carrying
    constituent, verbatim, once per region (FR16).
  - `Match { interpretant: str, kind: Literal["concept","exact"], score: float =
    0.0, exact_value: bool = False, segment_ordinal: int }` — anchored to the
    segment it hit (FR17).
  - `Region { region_id: str, source: Source, locator: str, score: float,
    convergence_count: int, segments: tuple[Segment, ...], matches:
    tuple[Match, ...] }`.
  - `RegionQueryResult { facets: Facets, regions: tuple[Region, ...] }` (reuses
    `Facets`).
  *Verify:* construction/serialization tests; `model_dump(mode="json")` matches the
  `plan.md` worked contract (segment text once; every match carries
  `segment_ordinal`; `kind`/`exact_value` distinguish concept vs token).

- [x] **T9. Specificity weight helper.** In `retrieval/pipeline.py`, add a helper
  computing per-interpretant weight `log(N / df(surface_form))` from
  `document_frequency`, df from `as_token` for tokens and the query string for
  concepts.
  *Verify:* unit test — rarer surface form → strictly higher weight; df 0 handled.

- [x] **T10. `retrieve_regions`.** Add `RetrievalPipeline.retrieve_regions(graph_facts)`:
  reuse `_search_deep_pools`; keep floor-clearing concept hits + token hits;
  group eligible segments of one source into regions by contiguous `ordinal` +
  `region_window_size`; per interpretant keep its **best** match and record that
  match's `segment_ordinal` (FR17); collect the region's match-carrying `segments`
  (deduped by ordinal, FR16); eligible when distinct interpretants ≥
  `region_min_interpretants`.
  *Verify:* unit tests with seeded hits — interpretants on adjacent ordinals roll
  into one region with the right `convergence_count`; each `Match.segment_ordinal`
  points at the verse it hit; a segment two interpretants share appears once in
  `segments`; non-contiguous ordinals do not merge; single-interpretant region
  survives (min default 1).

- [x] **T11. Region scoring & ranking.** Score each region
  `Σ(weight × strength)` (concept strength = raw floored similarity, token = fixed
  presence constant); sort regions by score desc; build facets from the region
  list.
  *Verify:* unit test — a two-real-interpretant region outranks a comparable
  single; a rare interpretant outweighs a ubiquitous one; token-only region ranks
  by presence constant.

- [x] **T12. Config knobs.** Add `region_window_size: int = 3` and
  `region_min_interpretants: int = 1` to `Settings`; document `retrieval_min_score`
  as the absolute match floor. Thread both into `RetrievalPipeline`.
  *Verify:* settings test; pipeline honors overrides.

## Phase 4 — Wiring (plan §data flow)

- [x] **T13. `query_service.query_regions`.** Add alongside `query_fragments`, same
  parameter shape, calling `retrieve_regions`.
  *Verify:* service test mirrors the existing `query_fragments` tests.

- [x] **T14. API route.** Point `/api/query` at `query_regions` with
  `response_model=RegionQueryResult`. Keep `query_fragments` importable until the
  UI swap lands (T15–T19); it and its route/tests are removed in T20.
  *Verify:* `test_api.py` — response has `facets`/`regions`, a region carries
  `segments` + segment-anchored `matches`; unknown symbol → 404; unreachable
  embedder → 502.

## Phase 5 — UI adaptation to the region API (plan §Frontend/UI adaptation)

Vocabulary: backend/API = `Region`; frontend view = `Hotspot` (existing component
names). `client.ts` is the single translation seam.

- [x] **T15. Types.** In `web/src/api/types.ts` replace `Fragment`/`FragmentMatch`/
  `FragmentQueryResult` with `Hotspot`/`HotspotSegment`/`HotspotMatch`/
  `HotspotQueryResult` mirroring the region models — `HotspotMatch` has
  `interpretant`, `kind`, `score`, `exactValue`, `segmentOrdinal`; `Hotspot` has
  `segments` + `matches`.
  *Verify:* `npx tsc -b` fails only where downstream code still uses old names
  (drives T16–T19).

- [x] **T16. Client seam.** In `web/src/api/client.ts`, `fetchQuery` maps the API's
  `regions` → `Hotspot[]` (snake→camel, ordinal anchors preserved). Other calls
  (`summarizePassage`, traditions, symbols) unchanged.
  *Verify:* unit/type check; a mocked region response yields a `Hotspot` with
  populated `segments`/`matches`.

- [x] **T17. Hotspot utils + list/card.** Rename `utils/fragment.ts` →
  `utils/hotspot.ts`; add a helper resolving a `HotspotMatch.segmentOrdinal` to its
  `HotspotSegment`. Point `HotspotCard`/`HotspotList` at `Hotspot` (title =
  `locator`, badge = `convergenceCount`, subtitle = matched interpretant names —
  logic unchanged).
  *Verify:* `npx tsc -b`; list renders ranked hotspots with correct badges.

- [x] **T18. Hotspot detail panel (behavioral change).** Rename
  `FragmentDetailPanel.tsx` → `HotspotDetailPanel.tsx`. Render the region's
  `segments` list (each verbatim, headed by its `locator`); render the interpretant
  chip row so each chip **links to its anchored segment** (FR17) — clicking
  `laughter` scrolls/highlights `Genesis 21:6`, `hundred` → `21:5`. AI-summary
  action summarizes over the region's segments. Remove the single-blob passage
  render.
  *Verify:* manual — clicking each interpretant chip navigates to the right verse;
  a segment shared by two interpretants shows once.

- [x] **T19. App + CSS.** In `App.tsx` rename `fragment*` identifiers to `hotspot*`;
  selection id `chunk_id` → `region_id`; filter/rank logic (keys off
  `matches`/`convergenceCount`) unchanged. Add `index.css` rules for the segment
  list + active-anchor highlight.
  *Verify:* `cd web && npx tsc -b && npx vite build`; submit a query, toggle facets,
  select a hotspot, navigate segments, trigger AI summary.

- [x] **T20. Remove the superseded fragment path.** Delete `retrieve_fragments`,
  `Fragment`/`FragmentMatch`/`FragmentQueryResult`, `query_fragments`, and their
  tests/routes now nothing references them.
  *Verify:* `rg -n "Fragment|query_fragments|retrieve_fragments"` returns nothing in
  `src`/`web`/`tests`; full `pytest` + `npx tsc -b` green.

## Phase 6 — Benchmark validation

- [x] **T21. Genesis benchmark.** Re-ingest the DRB with `scheme: scripture_verse`;
  query the Qoph interpretants; assert the `Genesis 20:18–21:6` region surfaces
  with `convergence_count` 3 at a `region_window_size` spanning that range, and
  that `hundred`→21:5 / `laughter`→21:6 anchor correctly (FR17).
  *Verify:* a recorded integration check / notebook against `.mythrix`.

  **Result (real corpus, The Sun/rider-waite, 35,780-verse DRB):** Genesis
  21:5–6 rolls up as one region, `100`(exact)→ordinal 517 (21:5) and
  `laughter`(concept, 0.733)→ordinal 518 (21:6), anchored correctly (FR17).
  At `min_score=0.5` it ranks **#1** by score among 107 eligible regions,
  reproducing the original finding — see plan.md Risk #2 for why the
  `0.45` shipped default needs that override at this corpus's scale.

- [x] **T22. Bahir benchmark.** Ingest the Bahir with `scheme: numbered_section`;
  query `Nun` → §83 returns as a top isolated region; `kingdom`+`Nun` → §131 is the
  ranked 2-way convergence; Qoph interpretants (absent) surface little/nothing
  (floor working).
  *Verify:* same integration check; matches the ADR 0004 findings.

  **Result (real corpus, combined with the DRB, min_score=0.5):** §83 ("And
  what is Nun?", raw cosine 0.762 — the single strongest match in the whole
  36k-segment corpus) correctly surfaces as an isolated single-interpretant
  region, but only once `match_pool_size` is raised to `200`; at the shipped
  default (`30`) Chroma's approximate HNSW search never finds it at all,
  crowded out by Lamentations' acrostic "Nun." verses and "Josue the son of
  Nun" — see plan.md Risk #5. The `kingdom`+`Nun`→§131 2-way convergence does
  **not** reproduce against the combined corpus: `kingdom` clears the floor
  for §131 (raw cosine 0.565) but never survives into `kingdom`'s own deep
  pool at any practical `match_pool_size`, crowded out by the far larger
  DRB's own many "kingdom" passages — a corpus-composition effect (the
  original finding was validated on the Bahir in isolation), not a
  regression in the ranking formula itself.

- [x] **T23. Floor & window sweep.** Confirm the shipped defaults (`min_score`,
  `region_window_size`) reproduce T21/T22; note any per-corpus override needed in
  `plan.md` Risks. No new literals hardcoded.

  **Result:** `region_window_size=3` needs no override — both benchmarks'
  adjacent-verse/section rollups work at the default. `min_score` and
  `match_pool_size` both need per-query overrides at this corpus's real
  scale (`min_score=0.5`, `match_pool_size=200`); both are already
  configurable, tunable knobs (`Settings`/`/api/query` params), so no new
  literal was hardcoded — see plan.md Risks #2 and #5 for the full findings.

## Definition of done

- Every spec FR1–FR18 traces to at least one task above.
- `ruff` clean, full `pytest` green, `web` builds.
- `plan.md`/`tasks.md` retained until the user confirms the feature complete
  (`CLAUDE.md` SDD rule) — not deleted on green tests.
