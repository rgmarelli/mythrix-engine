# Query Viewer Web UI — Plan

## Architecture

`api/` is a peer of `cli/` under `core/`, matching the relationship `cli/` already has with `core/`. Neither `api/` nor `cli/` imports from the other; shared logic lives in `core/`.

```
src/mythrix/
  core/
    bootstrap.py         # build_stores() — shared store construction
    query_service.py     # execute_query() (CLI), stream_query() (API)
    serialization.py     # facts_json_payload() — CLI --json shape
    retrieval/pipeline.py  # RetrievalPipeline.iter_candidates() — shared incremental retrieval
    graph/store.py        # + list_traditions(), list_symbols()
    models.py              # + SymbolSummary
  cli/
    commands/query.py    # run_query() — unchanged behavior, now a thin consumer of core/
    formatting.py         # render_facts_human/json — unchanged behavior
  api/
    app.py                # FastAPI() + lifespan + CORS + static mount
    dependencies.py       # get_stores(request)
    routes.py              # GET /api/traditions, /api/symbols, /api/query
    errors.py               # MythrixError -> HTTP status mapping
web/
  src/                    # React + TypeScript + Vite, independent toolchain
```

Two tools share one core library and two request surfaces: a Typer CLI process and a FastAPI HTTP process. Both call `core/bootstrap.py::build_stores` at startup and `core/query_service.py` per query.

## Verified operational constraint: Kùzu/Chroma concurrency

`KuzuGraphStore.__init__` (`core/graph/store.py`) constructs `kuzu.Database(str(db_path))` with no `read_only` flag — default is read-write. Kùzu permits exactly one `Database` handle per path in that mode. A second process opening the same path while another holds it raises immediately at construction: `RuntimeError: IO exception: Could not set lock on file: ...`.

`ChromaVectorStore.__init__` (`core/vector/store.py`) constructs `chromadb.PersistentClient(path=...)`, which takes no file lock. Concurrent writes against the same path are not prevented by Chroma itself.

The API's `lifespan` holds a write-mode `KuzuGraphStore` open for the process's full lifetime. Both `load-symbols` (`cli/commands/load_symbols.py`) and `load-documents` (`cli/commands/load_documents.py`) construct `KuzuGraphStore` before constructing `ChromaVectorStore` (the latter only reached if the former succeeds). A `load-*` invocation started while the API process is running fails at the Kùzu open, before it reaches Chroma. No locking code is added for v1; the API process must be stopped before running `load-symbols`/`load-documents` against the same `.mythrix/` directory (FR14).

## Core library changes

Behavior-preserving. Existing tests pass unmodified after these changes.

- `core/graph/store.py`: `KuzuGraphStore.list_traditions() -> tuple[Tradition, ...]`; `list_symbols() -> tuple[SymbolSummary, ...]`, grouping symbols that have at least one interpretation by slug.
- `core/models.py`: `SymbolSummary(MythrixModel)` — `slug: str`, `canonical_name: str`, `symbol_type: str`, `tradition_slugs: tuple[str, ...]`.
- `core/bootstrap.py` (new): `build_stores(settings: Settings) -> Stores`, extracted from `cli/commands/query.py::query()`'s store-construction lines. `Stores` is a frozen container of `graph_store`/`vector_store`/`embedder`.
- `core/retrieval/pipeline.py`: `RetrievalPipeline.retrieve` splits into `iter_candidates(graph_facts) -> Iterator[ConceptCandidates | ConceptPairCandidates]` (yields each concept's `ConceptCandidates` as its Chroma searches complete, then yields the existing sorted pair-candidate groups) and `retrieve(graph_facts) -> RetrievalContext` (collects `iter_candidates`'s output into the same `RetrievalContext` shape as before).
- `core/query_service.py` (new): `execute_query(...) -> RetrievalContext` for the CLI, extracted from `cli/commands/query.py::run_query`'s retrieval logic, propagating `MythrixError` instead of catching it. `stream_query(...) -> Iterator[tuple[str, dict]]` for the API — yields `("graph_facts", ...)` first (graph lookup happens before the first `yield`), then one `("concept_candidates", ...)`/`("pair_candidates", ...)` pair per item from `RetrievalPipeline.iter_candidates`. Payloads are each model's own `.model_dump(mode="json")`.
- `core/serialization.py` (new): `facts_json_payload(context: RetrievalContext) -> dict`, moved from `cli/formatting.py`'s private helpers. Used by the CLI's `--json` output only.

## Streaming design for `GET /api/query`

Server-Sent Events (`text/event-stream`). Event sequence:

1. `event: graph_facts` — `GraphFacts.model_dump(mode="json")`.
2. `event: concept_candidates` — one per concept with at least one retrieved passage, `ConceptCandidates.model_dump(mode="json")`. Each passage carries its own `source`/`tradition` inline (denormalized — no top-level `sources`/`traditions` dedup table, unlike the CLI's `--json`).
3. `event: pair_candidates` — one per convergence group, in existing strongest-first order, `ConceptPairCandidates.model_dump(mode="json")`.
4. `event: done` — `{}`, marks a normal end of stream.
5. `event: error` — in place of the next event, if a `MythrixError` is raised while iterating (e.g. `ModelUnavailableError`, FR10). `{"detail": str(exc)}`. Ends the stream.

`core/query_service.py::stream_query` calls `graph_store.get_interpretation(symbol, tradition)` before its first `yield`. The API route primes the generator with one `next()` call outside `StreamingResponse` construction:

```python
gen = stream_query(...)
first_type, first_payload = next(gen)
```

A `MythrixError` here (`SymbolNotFoundError`/`TraditionNotFoundError`/`InterpretationNotFoundError`, FR9) raises before any response is constructed — the standard `errors.py` exception-handler mapping applies (404/502/500 JSON). Once `next()` succeeds, the HTTP status is committed to 200; a `MythrixError` raised later (only reachable once the embedder is called inside `RetrievalPipeline.iter_candidates`, FR10) is reported as the `error` SSE event instead.

The route's body generator is a plain synchronous generator. Starlette runs a sync `body_iterator` via `iterate_in_threadpool` — the blocking Kùzu/Chroma/Ollama calls do not block the event loop for other requests.

## API package

- `GET /api/traditions` — `200`, array of `Tradition.model_dump(mode="json")`, `response_model=list[Tradition]`.
- `GET /api/symbols` — `200`, array of `SymbolSummary.model_dump(mode="json")`, `response_model=list[SymbolSummary]`. Powers the picker (FR2) — every symbol with at least one interpretation.
- `GET /api/query?symbol=&tradition=&top_k=&match_pool=` — `200`, `text/event-stream`, event sequence above. `Settings`-derived defaults for `top_k`/`match_pool` when omitted, mirroring the CLI's `--top-k`/`--match-pool`.
- Stores built once at process startup via `lifespan`, stored on `app.state`, read per-request via `dependencies.py::get_stores`.
- Error mapping (`errors.py`, source of truth `core/errors.py`): `SymbolNotFoundError`/`TraditionNotFoundError`/`InterpretationNotFoundError` → 404; `ModelUnavailableError`/`ModelRequestError`/`EmbeddingModelMismatchError` → 502; other `MythrixError` → 500. Body: `{"detail": str(exc)}`.
- `app.py` registers `app.include_router(routes.router, prefix="/api")` before the conditional `app.mount("/", StaticFiles(directory="web/dist", html=True))`. A `Mount("/")` registered first shadows every path, including `/api/*`. `StaticFiles.__init__` raises `RuntimeError` at construction if the directory is missing (`check_dir=True` default) — the mount is guarded by `if Path("web/dist").is_dir():`.
- OpenAPI: FastAPI's default `/docs`, `/redoc`, `/openapi.json`. `/api/query`'s `responses=` parameter documents the `text/event-stream` content with the event schemas above; its docstring lists the event sequence.

## Dependencies

- `fastapi` — new direct dependency.
- `uvicorn` — promoted from transitive (via `chromadb`) to direct.
- `httpx` — added to the dev group, for `starlette.testclient.TestClient`.

## Frontend

`web/` — React + TypeScript + Vite, independent toolchain and build. `api/client.ts` opens `new EventSource` against `/api/query` (all parameters in the URL, native GET support). Component state accumulates per SSE event: `graphFacts`, `conceptCandidates[]`, `pairCandidates[]`, appended as events land — sections render as their data arrives, not after a single blocking fetch. `PassageCard` renders source attribution and score only, never passage text (FR4); `PassageDetailPanel` is the only place text renders, set directly from the clicked card's already-denormalized passage object.

## Dev/prod serving

- Dev: `uv run uvicorn mythrix.api.app:app --reload` (port 8000) + `cd web && npm run dev` (Vite, port 5173). `CORSMiddleware` allows the Vite origin. `VITE_API_BASE_URL` is always absolute.
- Prod: FastAPI serves the built `web/dist` via `StaticFiles`, single process, no CORS.
