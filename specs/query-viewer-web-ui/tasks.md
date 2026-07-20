# Query Viewer Web UI — Tasks

## Core library (behavior-preserving)

- [x] T1: Add `SymbolSummary` to `core/models.py`.
- [x] T2: Add `KuzuGraphStore.list_traditions()` and `list_symbols()` to `core/graph/store.py`.
- [x] T3: Add `core/bootstrap.py` with `build_stores(settings) -> Stores`; update `cli/commands/query.py::query()` to use it.
- [x] T4: Refactor `RetrievalPipeline.retrieve` into `iter_candidates()` (generator) + `retrieve()` (thin consumer) in `core/retrieval/pipeline.py`. Existing pipeline tests pass unmodified.
- [x] T5: Add `core/query_service.py` with `execute_query(...)` (extracted from `cli/commands/query.py::run_query`) and `stream_query(...)`. Update `run_query` to call `execute_query`.
- [x] T6: Add `core/serialization.py` with `facts_json_payload(...)` (moved from `cli/formatting.py`). Update `render_facts_json` to use it.
- [x] T7: `uv run pytest` — confirm every existing test passes unmodified.

## API package

- [x] T8: `uv add fastapi`; promote `uvicorn` to a direct dependency; add `httpx` to the dev group.
- [x] T9: `src/mythrix/api/errors.py` — `MythrixError`-family to HTTP status mapping, registered as a FastAPI exception handler.
- [x] T10: `src/mythrix/api/dependencies.py` — `get_stores(request) -> Stores`.
- [x] T11: `src/mythrix/api/routes.py` — `GET /api/traditions`, `GET /api/symbols` (typed `response_model`), `GET /api/query` (SSE, next()-priming, `error`/`done` events, OpenAPI `responses=` documentation).
- [x] T12: `src/mythrix/api/app.py` — `FastAPI()` factory, `lifespan` calling `build_stores` once, `CORSMiddleware`, router registered before conditional `StaticFiles` mount.
- [x] T13: `tests/unit/test_api.py` — traditions/symbols endpoints, SSE event-sequence assertions, mid-stream `error` event, pre-stream 404.

## Frontend

- [x] T14: Scaffold `web/` (Vite + React + TypeScript), `package.json`, `tsconfig.json`, `.env.development`.
- [x] T15: `web/src/api/types.ts` — types mirroring the SSE event payload shapes.
- [x] T16: `web/src/api/client.ts` — `EventSource`-based query client; plain `fetch` for `/api/traditions`/`/api/symbols`.
- [x] T17: `web/src/components/SymbolTraditionPicker.tsx`.
- [x] T18: `web/src/components/GraphFactsPanel.tsx`, `ConceptCandidatesSection.tsx`, `PairCandidatesSection.tsx`, `PassageCard.tsx` (metadata only, no passage text).
- [x] T19: `web/src/components/PassageDetailPanel.tsx` (full text, full citation, no truncation).
- [x] T20: `web/src/App.tsx` — accumulating state wired to the SSE client, section rendering, passage selection.
- [x] T21: `web/.gitignore` / root `.gitignore` — `web/node_modules/`.

## Wiring and verification

- [x] T22: Confirm dev flow — `uv run uvicorn mythrix.api.app:app --reload` + `npm run dev`, CORS working, sections render progressively.
- [x] T23: `npm run build`; confirm `uv run uvicorn mythrix.api.app:app` serves `web/dist` standalone with `/api/*` still routing correctly.
- [x] T24: `uv run ruff check . && uv run ruff format --check .`.
- [x] T25: Manual check — unknown symbol/tradition surfaces a visible pre-stream error; embedder failure surfaces a visible mid-stream error.
- [x] T26: Manual check — `/docs` shows typed schemas for `/api/traditions`/`/api/symbols` and a documented `text/event-stream` response for `/api/query`.
- [x] T27: Manual check — running `load-symbols` while the API is up fails fast with the Kùzu lock error.

## Post-review UI fixes

- [x] T28: Rename section headings — "Candidates" → "Passages" (per-concept) / "Convergence" (per-pair) — in `ConceptCandidatesSection.tsx`/`PairCandidatesSection.tsx`.
- [x] T29: `GraphFactsPanel.tsx` — render each correspondence's target symbol's own `properties` and the relationship's `target_semantic_facts`, nested under the correspondence line; render the queried symbol's own `properties` above the interpretation attributes (FR16).
- [x] T30: `PassageCard.tsx` — show `{source.id} - {locator}` instead of `{source.title}, {source.author}`.
- [x] T31: `index.css` — bound `.passage-detail` to `max-height: calc(100svh - 2rem)` with `overflow-y: auto`.
- [x] T32: `PassageDetailPanel.tsx` — reorder metadata `<dl>` above the passage text.

## AI Summary action

- [x] T33: `core/synthesis/prompts.py::render_passage_summary_prompt(text, concepts)`.
- [x] T34: `api/dependencies.py::get_chat_client()` — per-request `OllamaChatClient`.
- [x] T35: `api/routes.py` — `SummarizeRequest`/`SummarizeResponse`, `POST /api/summarize`.
- [x] T36: `api/app.py` — `CORSMiddleware.allow_methods` includes `POST`.
- [x] T37: `tests/unit/test_api.py` — `/api/summarize` success (fake chat client) and model-unavailable 502.
- [x] T38: `App.tsx` — track `selectedConcepts` alongside `selectedPassage`; pass through from both section components.
- [x] T39: `api/client.ts::summarizePassage`; `PassageDetailPanel.tsx` — AI Summary button, loading/error/result states, remounted via `key={chunk_id}` per selection.
- [x] T40: Manual check — AI Summary button against real Ollama (`qwen2.5:3b`) produces a passage-focused summary end to end.

## Sign/Manifestation vocabulary catch-up + semiotic-system selector

- [x] T41: `core/models.py::SignSummary` — add `semiotic_system: str`; `core/graph/store.py::list_signs()` — select and populate it.
- [x] T42: `tests/unit/test_graph_store.py`/`test_api.py` — assert `semiotic_system` on the updated fixtures.
- [x] T43: Rewrite `web/src/api/types.ts` for the current `core/models.py` shapes: `Sign`, `Manifestation`, `Property`, `Interpretant`, `IntersemioticInterpretant`, `Source` (`id`/`domain`/`citation_label`/`description`), `RetrievedPassage` (no `tradition`), `GraphFacts` (`sign`/`manifestation`), `SignSummary` (`+ semiotic_system`).
- [x] T44: Rename `SymbolTraditionPicker.tsx` → `SignTraditionPicker.tsx`; add a semiotic-system `<select>` (FR20) that filters the sign list, resetting sign/tradition selections on change.
- [x] T45: `GraphFactsPanel.tsx` — update field access to `sign`/`manifestation`/`property`/`interpretant`/`intersemiotic_interpretants`; render the manifestation's own `properties` alongside the sign's.
- [x] T46: `PassageCard.tsx`/`PassageDetailPanel.tsx` — attribution via `source.citation_label || `${title}, ${author}``; drop the `Tradition` `<dl>` row (removed from `RetrievedPassage`).
- [x] T47: `App.tsx` — wire the renamed picker and updated types; no behavior change to streaming/selection state.
- [x] T48: `cd web && npx tsc -b && npx oxlint` clean; `npm run build` succeeds.
- [x] T49: Manual check — dev server renders a system → sign → tradition cascade, submits a query, and results match `mythrix query --json` for the same sign/tradition pair.
