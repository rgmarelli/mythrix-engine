# Convergence Rollup Retrieval — Plan

Technical approach for `spec.md`, grounded in the current codebase. Rationale for
the decisions below lives in `specs/architecture-decisions/` (ADR 0001–0005); this
plan is the *how*, not the *why*.

## Starting point: most of the machinery already exists

The `query-viewer-facet-redesign` work already shipped a **fragment/facet
pipeline** that this spec builds directly on top of. What is already true today:

- `RetrievalPipeline.retrieve_fragments()` returns a `FragmentQueryResult`
  (`facets` + one `Fragment` per chunk) — `src/mythrix/core/retrieval/pipeline.py`.
- **Per-interpretant live matching** already happens in `_search_deep_pools()`
  (one dense search per concept; exact-token via `document_contains`). No
  precompute — satisfies ADR 0003 as-is.
- **Isolated matches are already first-class**: `retrieve_fragments` emits
  fragments with `convergence_count` as low as 1 and sorts by
  `(convergence_count, max_match_score)`. ADR 0004's "no convergence gate" is
  already the behavior — no `min_interpretants ≥ 2` filter exists to remove.
- **An absolute similarity floor already exists**: `Settings.retrieval_min_score`
  (default `0.45`), applied on raw `1 - distance` in `_build_fragment` and
  eligibility. This *is* ADR 0004's floor; it only needs a small reframe, not
  invention.
- Exact-token filtering exists but uses **`$contains` (substring)** in
  `ChromaVectorStore.similarity_search`.

What the spec adds that does **not** exist yet — the real scope of this plan:

| Gap | Spec | Today |
|-----|------|-------|
| **Structural segmentation** | FR1–FR2 | `chunking.py` cuts fixed ~650-word paragraph windows; locator is a best-effort chapter *string*, no verse, no ordinal, no coordinates |
| **Region rollup over contiguous segments** | FR9–FR11 | Convergence is per-chunk + pairwise (FR27); no notion of a contiguous multi-segment region |
| **Specificity (lexical-IDF) weighting** | FR12–FR14 | Not present; ranking is `convergence_count` then best raw score |
| **Word-bounded / normalized token match** | FR7 | `$contains` substring (the `50`→`150` bug) |
| **Absolute floor, reframed pre-rollup** | FR6 | Exists as `min_score`; applied at fragment build, needs to gate segment matches before rollup |

## Affected modules

- `src/mythrix/core/vector/chunking.py` — add a structural segmenter alongside the
  existing word-count chunker.
- `src/mythrix/core/loaders/sign_schema.py` + `document_loader.py` — let a source
  declare its segmentation scheme; route ingestion through the segmenter.
- `src/mythrix/core/vector/store.py` — carry structural coordinates in metadata;
  word-bounded `$regex` matching; a `document_frequency()` count.
- `src/mythrix/core/retrieval/pipeline.py` — the rollup + specificity + region
  scoring, as a new path beside `retrieve_fragments`.
- `src/mythrix/core/models.py` — region/segment fields on the result models.
- `src/mythrix/core/config.py` — new knobs (window size, min-interpretants).
- `src/mythrix/core/query_service.py` + `api/routes.py` — expose the region path.

## Design by area

### A. Structural segmentation (FR1–FR2)

**Source declares its own structure** (keeps the core domain-agnostic, ADR 0001).
Add an optional block to `SourceBlock`:

```yaml
source:
  id: en_drb
  structure:
    scheme: scripture_verse      # named segmenter in a small core registry
```

Core ships a few generic, content-neutral segmenters keyed by `scheme`:

- `scripture_verse` — splits on the inline `chapter:verse.` markers already present
  in the DRB text; coordinates `(chapter, verse)`, one segment per verse.
- `numbered_section` — splits on leading `N.` markers (the Bahir); coordinate
  `(section)`, one segment per section.
- `paragraph` — blank-line paragraphs; coordinate `(ordinal only)`.

When no `structure` is declared, **fall back to the existing `chunk_text`** word-
count chunker unchanged — backward compatible; nothing forces a re-ingest.

A segmenter returns `Segment`s (extend the current `Chunk` model additively):
add `ordinal: int` (0-based position within the source, the contiguity key),
`section: str` (coarse label, e.g. `"Genesis 20"`), and keep `locator` (display,
e.g. `"Genesis 20:1"`). Per FR2 the structural-label prefix (`20:1.`, `83.`) is
**stripped from `text`** so it neither embeds nor triggers token containment.

### B. Coordinates in the store (FR2)

Extend `ChunkMetadata` / the per-chunk metadata dict / `VectorHit` with
`ordinal` and `section` (defaulted, so the word-count path still writes valid
rows). `chunk_index` already exists and can serve as `ordinal` for the fallback
path. Contiguity test: two hits are contiguous iff same `source_id` and
`|ordinal_a − ordinal_b| == 1`.

### C. Word-bounded, normalized token matching (FR7)

In `ChromaVectorStore.similarity_search`, switch the exact-token path from
`{"$contains": token}` to `{"$regex": r"\b" + re.escape(token) + r"\b"}` (local
Chroma supports `$regex`). Normalization stays curator-authored via
`query.as_token` (already the case — `"100"` authored as `"hundred"`); the change
is purely the word boundary. Same regex feeds area E's df count.

### D. Absolute match floor (FR6)

Reuse `retrieval_min_score` as the floor. It already gates on raw `1 - distance`.
Two adjustments: (1) apply it at the point a concept match enters a **region**
(not just fragment display); (2) confirm exact-token matches bypass it
(they already do — `exact_value` matches are added without a score check).
The default (`0.45`) is close to the Bahir-observed `~0.50`; leave the default,
document that it is embedding-model-specific and tunable per query.

### E. Specificity weighting (FR12–FR14)

New, and the most additive piece. Weight = `log(N_units / df(surface_form))`,
`df` from **literal** whole-word document frequency (ADR 0004), never dense
scores.

- Add `ChromaVectorStore.document_frequency(term) -> int` = count of chunks whose
  text matches the word-bounded `$regex` (Chroma `get(where_document=…)` +
  `count`). Compute once per interpretant per query.
- Behind a tiny interface so it can later be swapped for an **ingest-time df
  table** (allowed under ADR 0003 — corpus statistics, not match precompute) when
  the corpus is large enough that per-query regex counts hurt (see Risks).
- Surface form for a concept interpretant is its query string; for a token, its
  `as_token`.

### F. Region rollup (FR9–FR11)

New method `retrieve_regions(graph_facts) -> RegionQueryResult`, parallel to
`retrieve_fragments` (which stays for the current chunk-based UI until the swap):

1. `_search_deep_pools(graph_facts)` (reused unchanged) → per-interpretant hits,
   each carrying `ordinal`/`section`.
2. Keep only floor-clearing concept hits + token containment hits.
3. Group eligible segments of one source into **regions** by contiguity and a
   window of `region_window_size` consecutive ordinals (a section, or N verses).
   `region_window_size = 1` degenerates to per-segment.
4. Per region, per interpretant, keep the **best** surviving match.
5. `convergence_count` = distinct matching interpretants; eligible when
   `≥ region_min_interpretants` (default **1**).

### G. Region score & results (FR12–FR18)

- `score = Σ_matching_interpretants ( specificity_weight × strength )`, where
  concept `strength` = raw floor-clearing similarity and token `strength` = a
  fixed presence constant. Sort regions by `score` desc. Convergence rises out of
  the sum (ADR 0004) — no separate gate.
- **Introduce a first-class `Region` model** (decision on T8, below), *not* an
  overloaded `Fragment`. Three nested levels, matching the API contract:
  - `Region { region_id, source, locator, score, convergence_count, segments,
    matches }`
  - `Segment { ordinal, locator, text }` — each match-carrying constituent verse,
    verbatim, listed **once** per region (FR16).
  - `Match { interpretant, kind: "concept"|"exact", score, exact_value,
    segment_ordinal }` — every match **anchors to the segment it hit** (FR17), so
    `laughter → 21:6`, `hundred → 21:5`. `matches` reference `segments` by
    `ordinal` (normalized, no text duplication).
  - `RegionQueryResult { facets, regions }`. `Facets` is reused unchanged.
- The `Fragment`/`retrieve_fragments` path is **superseded**, not co-maintained:
  removed once the UI swaps to regions (see Backward compatibility).

**T8 model decision (settled).** Clean `Region`/`Segment`/anchored-`Match` in the
backend, spec, and API; the frontend keeps its existing **`Hotspot`** component
vocabulary (`HotspotCard`/`HotspotList` already exist) and maps `regions →
Hotspot[]` at the single seam in `client.ts`. This pays a bounded one-time rename
(the frontend has ~193 `fragment` references) to end with a model whose name never
lies — chosen over overloading `Fragment` because the region path supersedes the
chunk path permanently, so a `Fragment`-named region would be lasting stale naming.

**Worked API contract** (`GET /api/query`, `(child, laughter, hundred)` over the
DRB, real verses):

```json
{
  "facets": { "sources": [{"id":"en_drb","label":"Douay-Rheims Bible","count":12}],
              "interpretants": [{"value":"laughter","count":3},{"value":"hundred","count":5}] },
  "regions": [{
    "region_id": "en_drb::Genesis:21:5-6",
    "source": {"id":"en_drb","label":"Douay-Rheims Bible"},
    "locator": "Genesis 21:5–6", "score": 8.42, "convergence_count": 3,
    "segments": [
      {"ordinal":517,"locator":"Genesis 21:5","text":"When he was a hundred years old..."},
      {"ordinal":518,"locator":"Genesis 21:6","text":"And Sara said: God hath made a laughter for me..."}
    ],
    "matches": [
      {"interpretant":"laughter","kind":"concept","score":0.61,"exact_value":false,"segment_ordinal":518},
      {"interpretant":"child","kind":"concept","score":0.58,"exact_value":false,"segment_ordinal":518},
      {"interpretant":"hundred","kind":"exact","exact_value":true,"segment_ordinal":517}
    ]
  }]
}
```

## Data flow (end to end)

```
ingest:  source.txt + structure.scheme
           → segmenter → Segment{text, ordinal, section, locator}
           → embed → ChromaVectorStore.add_chunks (coords in metadata)

query:   sign+tradition → GraphFacts (Kùzu)
           → build_query_texts (per-interpretant, unchanged)
           → _search_deep_pools (dense + $regex token, unchanged)
           → floor (min_score) → eligible segment matches
           → rollup by contiguity + window  → regions
           → specificity weight (df) → Σ score → rank
           → RegionQueryResult (facets + ranked regions)  → API/CLI/UI
```

## New config knobs (`Settings`)

- `region_window_size: int = 3` — contiguous segments per region window.
- `region_min_interpretants: int = 1` — isolated matches first-class (ADR 0004).
- `retrieval_min_score` — unchanged, now documented as the absolute match floor.

## Frontend / UI adaptation (plan §data flow, area G)

The current UI consumes the flat `Fragment` shape; the region API is a **nested**
shape (region → segments → segment-anchored matches). The query viewer adapts as
follows — the `Hotspot` vocabulary stays, the data behind it becomes a region.

- **`web/src/api/types.ts`** — replace `Fragment`/`FragmentMatch`/
  `FragmentQueryResult` with `Hotspot`/`HotspotSegment`/`HotspotMatch`/
  `HotspotQueryResult`, mirroring `Region`/`Segment`/`Match`/`RegionQueryResult`.
  A `HotspotMatch` carries `interpretant`, `kind`, `score`, `exact_value`,
  `segmentOrdinal`; a `Hotspot` carries `segments` + `matches`.
- **`web/src/api/client.ts`** — the single translation seam: `fetchQuery` maps the
  API's `regions` to `Hotspot[]`. `summarizePassage` and the other calls unchanged.
- **`web/src/utils/fragment.ts` → `utils/hotspot.ts`** — rename; adjust helpers to
  the nested shape (e.g. a helper resolving a match's `segmentOrdinal` to its
  `HotspotSegment`).
- **`HotspotCard` / `HotspotList`** — already region-shaped conceptually (title =
  region `locator`, badge = `convergence_count`, subtitle = matched interpretant
  names). Point them at the new type; badge/rank logic is unchanged since
  `matches`/`convergence_count` carry over.
- **`FragmentDetailPanel.tsx` → `HotspotDetailPanel.tsx`** — the real behavioral
  change: render the region's `segments` list (each verbatim, headed by its
  `locator`), and render the interpretant chip row so each chip **links to its
  anchored segment** (FR17) — clicking `laughter` scrolls/highlights `Genesis
  21:6`, `hundred` → `21:5`. The AI-summary action now summarizes over the region's
  segments. Removes the old single-blob passage render.
- **`App.tsx`** — state/filter logic keys off `matches`/`convergence_count`
  (unchanged); rename `fragment*` identifiers to `hotspot*`; selection id moves
  from `chunk_id` to `region_id`.
- **`index.css`** — add rules for the per-segment list and the active-anchor
  highlight; existing facet/hotspot-card/detail rules mostly carry over.

Verification: `cd web && npx tsc -b && npx vite build`, then exercise against a
real `.mythrix` store — submit a query, confirm a region shows its segments and
that clicking an interpretant chip navigates to the correct verse.

## Key trade-offs

- **Verse granularity multiplies vector count** (ADR 0001/0005). Accepted; the
  scale question is a spike, not a blocker, and the fallback chunker means
  existing corpora keep working un-migrated.
- **Query-time df is O(interpretants) regex scans** (ADR 0004/0005). Fine now,
  abstracted for an ingest-time df table later.
- **RRF stays inside a concept** (plain vs filtered variants) — this is *not* the
  cross-channel lexical RRF ADR 0002 rejects; it fuses one concept's own dense
  rankings. Left as-is.

## Risks / spikes (resolve during implementation)

1. **Chroma at verse-scale + cheap df** — the ADR 0005 spike. Resolved: full
   verse-level ingestion of the DRB (35,780 segments) plus the Bahir (200)
   succeeded once `ChromaVectorStore.add_chunks` batched its own `upsert()`
   calls to the client's `get_max_batch_size()` (Chroma rejects one call
   larger than that outright — a real failure the fine-grained segmenter
   exposed, since the old word-count chunker never produced enough chunks
   from one document to hit it). `document_frequency()`'s per-query `$regex`
   scan stayed fast enough at this scale not to need an ingest-time table.
2. **Floor value across corpora** — `0.45` was tuned on the DRB in isolation;
   confirmed against the real combined DRB+Bahir corpus (36k segments) that
   `0.45` lets weak (~0.46-0.49) concept matches combine with the "hundred"
   exact-token filter to let genealogy-dense books (Esdras, Machabees —
   dense with numeric mentions) outrank Genesis 21. Overriding to `~0.50`
   (already the Bahir-derived value ADR 0004 recorded) restores Genesis
   21:5–6 to rank 1 for The Sun/Qoph. Confirms the floor must stay a tunable,
   per-corpus knob, not a single hardcoded default that suits every corpus.
3. **Window default** — `3` is a starting guess; confirmed against the real
   Genesis 21:5/21:6 case (adjacent ordinals 517/518 correctly roll up into
   one region, `hundred`→21:5 and `laughter`→21:6 anchored to their own
   segments).
4. **Frontend rename churn** — the T8 decision (clean `Region` backend + `Hotspot`
   UI) requires renaming the frontend's ~193 `fragment` references and reshaping
   the view model from a flat fragment to a nested region (segments + anchored
   matches). Mechanical, type-checker-guided, but a real pass — see Frontend/UI
   adaptation below. Not a blocker, but the largest single chunk of UI work.
5. **HNSW recall at combined-corpus scale, and cross-corpus concept crowding.**
   Confirmed empirically querying Nun against the combined corpus: (a) Chroma's
   HNSW is approximate, not exact — Bahir §83 (raw cosine 0.762, the single
   best match in the whole 36k-segment corpus for "Nun") is invisible at
   `match_pool_size=30`/`60`/`100` and only surfaces at `top_k=200`, since
   Lamentations' acrostic verses ("Nun. Let us lift up our hearts...") and
   "Josue the son of Nun" references draw HNSW's approximate search away from
   the sparse Bahir cluster; (b) a niche corpus mixed with a much larger,
   thematically-overlapping one can lose a genuine concept match entirely to
   crowding — "kingdom" clears the match floor for the Bahir's §131 (raw
   cosine 0.565) but never survives into "kingdom"'s own deep pool at any
   practical `match_pool_size`, because the far larger DRB supplies hundreds
   of segments about kingdoms that rank higher. Neither is a ranking-formula
   bug: (a) is resolved by raising `match_pool_size` for a query expected to
   need broad recall (confirmed: `match_pool_size=200` surfaces §83 as the
   correct isolated top Bahir match); (b) has no config fix — it is a genuine
   consequence of merging a small special-interest corpus with a much larger
   general one under FR7's single shared corpus model, worth a future look
   (e.g. per-source-scoped queries) but out of scope here.

## Backward compatibility & migration

- Sources without a `structure` block are unaffected (fallback chunker).
- Re-ingesting a source *with* a new `structure` block is already handled by the
  content-hash replace path (`load_document`, FR3) — changed input replaces that
  source's rows.
- `retrieve_fragments`/`Fragment`/`query_fragments` and the `Fragment`-shaped
  `/api/query` response existed only until the UI swapped to regions (T15-T19);
  removed in T20, per the T8 decision, rather than co-maintained.

## Out of scope / deferred

- Migrating off Chroma (only if the spike fails — ADR 0005).
- Ingest-time df table (introduce only when query-time df hurts).
- Merging this spec into `symbol-interpretation-core` — a separate,
  documentation-only decision, independent of this implementation.

## Sequencing (detail lands in `tasks.md`)

1. Segmenter + source `structure` declaration + coordinates in store (areas A/B).
2. Word-bounded `$regex` + `document_frequency` (areas C/E-store).
3. `retrieve_regions` rollup + specificity score + result model (areas D/F/G).
4. `query_service` + `routes` region path; then UI swap to the `Hotspot`/region
   shape (types → client → utils → cards → detail panel → App/CSS); remove the
   superseded `Fragment` path.
5. Validate on the Genesis (`child/laughter/hundred` → `20:18–21:6`) and Bahir
   (`Nun` → §83 isolated; `kingdom`+`Nun` → §131) benchmarks.
