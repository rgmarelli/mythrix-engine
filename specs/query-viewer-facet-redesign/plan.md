# Query Viewer Facet/Fragment Redesign — Plan

## Architecture

No change to the `core`/`cli`/`api`/`web` split established in `specs/query-viewer-web-ui/plan.md`. `cli/commands/query.py` continues to call `core/query_service.py::execute_query`, unchanged. The API gets a new code path through `core/retrieval/pipeline.py` and a new `core/query_service.py` function, replacing `GET /api/query`'s current SSE contract with a single JSON response.

## Data model (`core/models.py`)

Added after `RetrievalContext`, alongside the existing `ConceptCandidates`/`ConceptMatchScore`/`MergedCandidate`/`ConceptPairCandidates`/`RetrievalContext`/`GraphFacts` (all retained, unchanged, for the CLI path):

```python
class FragmentMatch(MythrixModel):
    interpretant: str
    score: float = 0.0
    exact_value: bool = False

class Fragment(MythrixModel):
    chunk_id: str
    source: Source
    text: str
    locator: str = ""
    chunk_index: int = 0
    char_start: int = 0
    char_end: int = 0
    embedding_model: str = ""
    matches: tuple[FragmentMatch, ...] = ()
    convergence_count: int = 0

class SourceFacet(MythrixModel):
    id: str
    label: str
    count: int

class InterpretantFacet(MythrixModel):
    value: str
    count: int

class Facets(MythrixModel):
    sources: tuple[SourceFacet, ...] = ()
    interpretants: tuple[InterpretantFacet, ...] = ()

class FragmentQueryResult(MythrixModel):
    facets: Facets
    fragments: tuple[Fragment, ...] = ()
```

## Retrieval pipeline (`core/retrieval/pipeline.py`)

`RetrievalPipeline.iter_candidates`'s per-concept RRF search loop (building `deep_hits_by_concept: dict[str, dict[str, VectorHit]]` and `filter_token_chunk_ids: dict[str, set[str]]`) is extracted into:

```python
def _search_deep_pools(self, graph_facts: GraphFacts) -> tuple[dict[str, dict[str, VectorHit]], dict[str, set[str]]]
```

`iter_candidates` calls this method; its own behavior and output are unchanged.

A new method:

```python
def retrieve_fragments(self, graph_facts: GraphFacts) -> FragmentQueryResult
```

Algorithm:

1. Call `_search_deep_pools(graph_facts)`.
2. For each interpretant's deep pool, take its first `top_k` entries (RRF-rank order) and keep those whose similarity score is `>= min_score`. The union of `chunk_id`s across every interpretant's kept slice is the eligible fragment set.
3. For each eligible `chunk_id`, build its `matches` list:
   - For every interpretant, if that `chunk_id` is in the interpretant's deep pool and its similarity score for that chunk is `>= min_score`, append a `FragmentMatch(interpretant=..., score=..., exact_value=False)`.
   - For every recognized filter token, if `chunk_id` is in that token's `filter_token_chunk_ids` set, append `FragmentMatch(interpretant=<token value>, score=0.0, exact_value=True)`, unconditionally of `min_score`.
4. `convergence_count` = count of `matches` where `exact_value` is `False` (FR3: an exact-value match is a literal-containment guarantee, not a semantic signal, so it is reported in `matches` but does not count toward convergence — mirrors `_build_pair_candidates`'s existing rule that a filter token "contributes membership but no score").
5. Hydrate each eligible chunk's `RetrievedPassage` fields (`_hydrate`, unchanged) into a `Fragment`, attaching its `matches` and `convergence_count`.
6. Sort fragments by `(convergence_count, max(match.score for match in matches))`, descending.
7. Build `Facets`: `sources` — one `SourceFacet` per distinct `fragment.source.id` among the fragment list, `count` = number of fragments with that source; `interpretants` — one `InterpretantFacet` per distinct `match.interpretant` across every fragment's `matches` (including exact-value ones, so they stay filterable), `count` = number of fragments containing that interpretant in `matches`.
8. Return `FragmentQueryResult(facets=facets, fragments=tuple(sorted_fragments))`.

`iter_candidates`, `retrieve`, `_build_pair_candidates`, `_hydrate`, `_source_for` are unchanged.

## `core/query_service.py`

`execute_query` unchanged. `stream_query` removed. Added:

```python
def query_fragments(
    *, symbol: str, tradition: str, graph_store: KuzuGraphStore, vector_store: ChromaVectorStore,
    embedder: Embedder, top_k: int, match_pool_size: int, merge_top_k: int, min_score: float,
) -> FragmentQueryResult:
    graph_facts = graph_store.get_manifestation(symbol, tradition)
    pipeline = RetrievalPipeline(graph_store=graph_store, vector_store=vector_store, embedder=embedder,
                                  top_k=top_k, match_pool_size=match_pool_size, merge_top_k=merge_top_k,
                                  min_score=min_score)
    return pipeline.retrieve_fragments(graph_facts)
```

## API (`api/routes.py`, `api/errors.py`)

`GET /api/query?symbol=&tradition=&top_k=&match_pool=` becomes a plain JSON endpoint, `response_model=FragmentQueryResult`, calling `query_fragments` with the same `Settings`-derived defaults as today. Removed: `DoneEventData`, `ErrorEventData`, `_query_event_schema`, `_format_sse`, `_sse_body`, and the `StreamingResponse`/`Iterator`/`json`/`models_json_schema` imports they required. `SignNotFoundError`/`TraditionNotFoundError`/`ManifestationNotFoundError`/`ModelUnavailableError`/`ModelRequestError` raised inside `query_fragments` are handled by the existing registered `MythrixError` exception handler (`errors.py`), same 404/502 mapping as `/api/traditions`/`/api/symbols`. `errors.py`'s module docstring is updated to remove its reference to `/api/query`'s SSE error-event behavior. `GET /api/traditions`, `GET /api/symbols`, `POST /api/summarize` are unchanged.

## Frontend (`web/src/`)

### `api/types.ts`

Removed: `Property`, `QueryDirective`, `Interpretant`, `Citation`, `IntersemioticInterpretant`, `Sign`, `Manifestation`, `GraphFacts`, `RetrievedPassage`, `ConceptCandidates`, `ConceptMatchScore`, `MergedCandidate`, `ConceptPairCandidates`. Retained: `Tradition`, `Source`, `SignSummary`. Added, mirroring the new backend models:

```ts
export interface FragmentMatch { interpretant: string; score: number; exact_value: boolean; }
export interface Fragment {
  chunk_id: string; source: Source; text: string; locator: string;
  chunk_index: number; char_start: number; char_end: number; embedding_model: string;
  matches: FragmentMatch[]; convergence_count: number;
}
export interface SourceFacet { id: string; label: string; count: number; }
export interface InterpretantFacet { value: string; count: number; }
export interface Facets { sources: SourceFacet[]; interpretants: InterpretantFacet[]; }
export interface FragmentQueryResult { facets: Facets; fragments: Fragment[]; }
```

### `api/client.ts`

`streamQuery`/`QueryStreamHandlers` removed. Added `fetchQuery(symbol: string, tradition: string, opts?: {topK?: number; matchPool?: number}): Promise<FragmentQueryResult>`, a plain `fetch` via the existing `fetchJson<T>` helper. `fetchTraditions`, `fetchSymbols`, `summarizePassage` unchanged.

### Components (`components/`)

Removed: `GraphFactsPanel.tsx`, `ConceptCandidatesSection.tsx`, `PairCandidatesSection.tsx`, `PassageCard.tsx`, `PassageDetailPanel.tsx`.

Retained unchanged: `SignTraditionPicker.tsx`.

Added:

- `FacetRow.tsx` — props `title: string`, `allLabel: string`, `options: {id: string; label: string; count: number}[]`, `selected: string | null`, `onSelect: (id: string | null) => void`. Used for both the Sources and Interpretants rows.
- `HotspotCard.tsx` — props `fragment: Fragment`, `isActive: boolean`, `onSelect: () => void`. Renders title, convergence badge, matched-interpretant subtitle.
- `HotspotList.tsx` — props `headerText: string`, `fragments: Fragment[]`, `selectedChunkId: string | null`, `onSelect: (chunkId: string) => void`. Renders `headerText` then a `HotspotCard` per fragment.
- `FragmentDetailPanel.tsx` — props `fragment: Fragment | null`, `activeInterpretant: string | null`, `onPrev: () => void`, `onNext: () => void`, `canGoPrev: boolean`, `canGoNext: boolean`. Renders breadcrumb, title + convergence badge, interpretant chip row (chips matching `activeInterpretant` styled active, others styled dimmed with an inline note, none omitted), a "Generate AI summary" button calling `summarizePassage(fragment.text, fragment.matches.map(m => m.interpretant))` and rendering the result in a distinct box, plain fragment text, and a footer with prev/next-hotspot buttons and a copy-ref button. Reuses the AI-summary `useState` trio (`summary`, `isSummarizing`, `summaryError`) from the removed `PassageDetailPanel.tsx`; mounted with `key={fragment.chunk_id}`.

### `App.tsx`

State: `signs`, `traditions`, `loadError`, `selectedSystem`, `selectedSymbol`, `selectedTradition` (unchanged) plus `queryResult: FragmentQueryResult | null`, `isQuerying: boolean`, `queryError: string | null`, `selectedSourceId: string | null`, `selectedInterpretant: string | null`, `selectedFragmentId: string | null`.

`handleSubmit` calls `fetchQuery(selectedSymbol, selectedTradition)`, resets `selectedSourceId`/`selectedInterpretant`/`selectedFragmentId` on submit, sets `queryResult` on success or `queryError` on failure.

Derived (`useMemo`):

```ts
const filteredFragments = queryResult.fragments.filter(f =>
  (selectedSourceId === null || f.source.id === selectedSourceId) &&
  (selectedInterpretant === null || f.matches.some(m => m.interpretant === selectedInterpretant))
);
const rankedFragments = [...filteredFragments].sort((a, b) => {
  if (a.convergence_count !== b.convergence_count) return b.convergence_count - a.convergence_count;
  return tieBreakScore(b) - tieBreakScore(a);
});
```

`tieBreakScore(fragment)` returns the matching entry's score for `selectedInterpretant` when set, else the fragment's maximum match score.

A `useEffect` sets `selectedFragmentId` to `rankedFragments[0]?.chunk_id ?? null` whenever the current `selectedFragmentId` is absent from `rankedFragments`.

Header text function `hotspotHeaderText(sourceLabel: string | null, interpretantValue: string | null)` implements four cases: no filters, interpretant only, source only, source and interpretant both.

Prev/next: index lookup in `rankedFragments`; buttons disabled at index 0 / last index (no wraparound).

Render tree: header (`h1` + `SignTraditionPicker`), two `FacetRow`s (Sources, Interpretants), a two-column grid of `HotspotList` and `FragmentDetailPanel`.

### `index.css`

Added classes, built from the existing custom properties (`--text`, `--text-h`, `--bg`, `--panel-bg`, `--border`, `--accent`, `--accent-bg`, `--error`, `--error-bg`): `.facet-row`, `.chip`, `.chip.active`; `.hotspot-list`, `.hotspot-card`, `.hotspot-card.active`, `.hotspot-card .badge`, `.hotspot-card .subtitle`; `.fragment-detail`, `.fragment-detail .breadcrumb`, `.fragment-detail .title-row` (renamed from `.passage-detail`, same sticky/scroll rules); `.interpretant-chip`, `.interpretant-chip.active`, `.interpretant-chip.dimmed`; `.ai-summary-button`, `.ai-summary-box`; `.fragment-footer`.

## Assumed defaults

- Fragment title: `locator || source.citation_label || source.title`.
- Facet source chip label: `source.title`. Fragment-detail breadcrumb: `` `${source.title} (${source.citation_label})` `` when `citation_label` is non-empty, else `source.title`.
- Prev/next hotspot buttons disable at list boundaries; no wraparound.
- AI summary is requested with every interpretant in `fragment.matches`, not only the active filter's interpretant.

## Behavior change from `specs/query-viewer-web-ui`

A fragment that does not rank within any interpretant's own displayed `top_k` slice is excluded from `FragmentQueryResult.fragments`, even if it appears in two or more interpretants' deeper `match_pool_size` pools. The prior SSE contract's `ConceptPairCandidates` could surface such a fragment; the new contract cannot.
