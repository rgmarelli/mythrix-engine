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
