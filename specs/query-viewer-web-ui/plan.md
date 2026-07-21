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
    graph/store.py        # + list_traditions(), list_signs()
    models.py              # + SignSummary
  cli/
    commands/query.py    # run_query() — unchanged behavior, now a thin consumer of core/
    formatting.py         # render_facts_human/json — unchanged behavior
  api/
    app.py                # FastAPI() + lifespan + CORS (GET, POST) + static mount
    dependencies.py       # get_stores(request), get_chat_client()
    routes.py              # GET /api/traditions, /api/symbols, /api/query, POST /api/summarize
    errors.py               # MythrixError -> HTTP status mapping
web/
  src/                    # React + TypeScript + Vite, independent toolchain
```

Two tools share one core library and two request surfaces: a Typer CLI process and a FastAPI HTTP process. Both call `core/bootstrap.py::build_stores` at startup and `core/query_service.py` per query.

## Verified operational constraint: Kùzu/Chroma concurrency

`KuzuGraphStore.__init__` (`core/graph/store.py`) constructs `kuzu.Database(str(db_path))` with no `read_only` flag — default is read-write. Kùzu permits exactly one `Database` handle per path in that mode. A second process opening the same path while another holds it raises immediately at construction: `RuntimeError: IO exception: Could not set lock on file: ...`.

`ChromaVectorStore.__init__` (`core/vector/store.py`) constructs `chromadb.PersistentClient(path=...)`, which takes no file lock. Concurrent writes against the same path are not prevented by Chroma itself.

The API's `lifespan` holds a write-mode `KuzuGraphStore` open for the process's full lifetime. Both `load-symbols` (`cli/commands/load_symbols.py`) and `load-documents` (`cli/commands/load_documents.py`) construct `KuzuGraphStore` before constructing `ChromaVectorStore` (the latter only reached if the former succeeds). A `load-*` invocation started while the API process is running fails at the Kùzu open, before it reaches Chroma. No locking code is added for v1; the API process must be stopped before running `load-symbols`/`load-documents` against the same `.mythrix/` directory (FR14). `POST /api/reload-symbols` (FR21) sidesteps this entirely for structured-data reloads specifically: it calls `core/loaders/sign_loader.py::load_directory` against the *same* `KuzuGraphStore` instance `lifespan` already constructed (via `Stores`/`get_stores`), rather than constructing a second one — there is only ever one `Database` handle in play, so no lock contention exists to work around. `load-documents`/Chroma reloads have no equivalent yet.

## Core library changes

Behavior-preserving. Existing tests pass unmodified after these changes.

- `core/graph/store.py`: `KuzuGraphStore.list_traditions() -> tuple[Tradition, ...]`; `list_signs() -> tuple[SignSummary, ...]`, grouping signs that have at least one manifestation by slug.
- `core/models.py`: `SignSummary(MythrixModel)` — `slug: str`, `canonical_name: str`, `sign_type: str`, `semiotic_system: str`, `tradition_slugs: tuple[str, ...]`. `semiotic_system` lets the picker offer a semiotic-system selector that scopes the sign list (FR20).
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

`core/query_service.py::stream_query` calls `graph_store.get_manifestation(symbol, tradition)` before its first `yield`. The API route primes the generator with one `next()` call outside `StreamingResponse` construction:

```python
gen = stream_query(...)
first_type, first_payload = next(gen)
```

A `MythrixError` here (`SignNotFoundError`/`TraditionNotFoundError`/`ManifestationNotFoundError`, FR9) raises before any response is constructed — the standard `errors.py` exception-handler mapping applies (404/502/500 JSON). Once `next()` succeeds, the HTTP status is committed to 200; a `MythrixError` raised later (only reachable once the embedder is called inside `RetrievalPipeline.iter_candidates`, FR10) is reported as the `error` SSE event instead.

The route's body generator is a plain synchronous generator. Starlette runs a sync `body_iterator` via `iterate_in_threadpool` — the blocking Kùzu/Chroma/Ollama calls do not block the event loop for other requests.

## API package

- `GET /api/traditions` — `200`, array of `Tradition.model_dump(mode="json")`, `response_model=list[Tradition]`.
- `GET /api/symbols` — `200`, array of `SignSummary.model_dump(mode="json")`, `response_model=list[SignSummary]`. Powers the picker (FR2, FR20) — every sign with at least one manifestation, each carrying its `semiotic_system` so the picker can offer a system selector without a separate endpoint.
- `GET /api/query?symbol=&tradition=&top_k=&match_pool=` — `200`, `text/event-stream`, event sequence above. `Settings`-derived defaults for `top_k`/`match_pool` when omitted, mirroring the CLI's `--top-k`/`--match-pool`. Query parameter names (`symbol`, `tradition`) and route paths (`/api/symbols`, `/api/traditions`) keep the pre-rename vocabulary deliberately — this is user/API-facing surface, not the authoring/domain-modeling vocabulary `core/models.py` uses internally (`Sign`, `Manifestation`, ...).
- `POST /api/reload-symbols?path=` (FR21) — `200`, `ReloadSymbolsResponse` (`traditions`/`sources`/`signs`/`manifestations`/`intersemiotic_interpretants` counts, mirroring `mythrix load-symbols`'s own summary, via the shared `sign_loader.py::summarize_plan`). `path` defaults to `Settings.symbols_data_path` (`data/semiotic_systems`) when omitted. Not called by the frontend (FR12) — a manual/`curl`/API-client trigger only.
- Stores built once at process startup via `lifespan`, stored on `app.state`, read per-request via `dependencies.py::get_stores`.
- Error mapping (`errors.py`, source of truth `core/errors.py`): `SignNotFoundError`/`TraditionNotFoundError`/`ManifestationNotFoundError` → 404; `ModelUnavailableError`/`ModelRequestError`/`EmbeddingModelMismatchError` → 502; `IngestValidationError` → 422; other `MythrixError` → 500. Body: `{"detail": str(exc)}`.
- `app.py` registers `app.include_router(routes.router, prefix="/api")` before the conditional `app.mount("/", StaticFiles(directory="web/dist", html=True))`. A `Mount("/")` registered first shadows every path, including `/api/*`. `StaticFiles.__init__` raises `RuntimeError` at construction if the directory is missing (`check_dir=True` default) — the mount is guarded by `if Path("web/dist").is_dir():`.
- OpenAPI: FastAPI's default `/docs`, `/redoc`, `/openapi.json`. `/api/query`'s `responses=` parameter documents the `text/event-stream` content with the event schemas above; its docstring lists the event sequence.

## AI Summary action (FR17-FR19)

`POST /api/summarize` — request `{passage_text: str, concepts: list[str]}`, response `{summary: str}`. Both are plain `pydantic.BaseModel`s local to `routes.py` (API transport shapes, not domain models — nothing in `core/models.py`).

`core/synthesis/prompts.py::render_passage_summary_prompt(text, concepts) -> str` builds a single-passage, marker-free prompt ("Summarize the following passage, focusing on the concepts: ...") — distinct from `SYSTEM_PROMPT`/the retired per-concept synthesis, which used `[G#]`/`[S#]` markers over the full graph-facts/passages context. This is a one-shot summary of text the caller already has in hand, not a citation-bearing claim to validate.

`api/dependencies.py::get_chat_client() -> ChatClient` constructs an `OllamaChatClient` (`core/synthesis/chain.py`, previously unused on any live path) fresh per request, unlike `get_stores`. `generation_model` (`core/config.py`) has no default, and `OllamaChatClient.__init__` validates the model against Ollama synchronously — building it once at process startup (alongside `Stores`, in `lifespan`) would fail API startup for every deployment that never sets a generation model or never clicks AI Summary. Building it lazily means the cost (and failure mode) is paid only when the action is actually used.

`summarize_passage` (`routes.py`) takes `chat_client: ChatClient = Depends(get_chat_client)`, builds the prompt, and returns `chat_client.invoke(prompt)` wrapped in the response model. `ModelUnavailableError`/`ModelRequestError` raised by either the dependency or `.invoke()` are caught by the same registered `MythrixError` exception handler as every other route (502, FR19) — no separate error path needed.

`app.py`'s `CORSMiddleware` allows `["GET", "POST"]` (was `["GET"]`) — the only mutating-looking request in v1, though it triggers no write to `.mythrix/`; it only calls out to Ollama.

## Dependencies

- `fastapi` — new direct dependency.
- `uvicorn` — promoted from transitive (via `chromadb`) to direct.
- `httpx` — added to the dev group, for `starlette.testclient.TestClient`.

## Frontend

`web/` — React + TypeScript + Vite, independent toolchain and build. `api/types.ts` mirrors `core/models.py`'s current shapes directly: `Sign`, `Manifestation`, `Property`, `Interpretant`, `IntersemioticInterpretant`, `Source` (with `domain`/`citation_label`/`description`), `RetrievedPassage` (no `tradition` field — a passage always comes from an independent corpus source), `GraphFacts` (`sign`/`manifestation`), `SignSummary` (`+ semiotic_system`). Display copy keeps the pre-rename words ("Symbol", "Correspondence") where the CLI's own human-readable rendering (`synthesis/prompts.py::graph_fact_lines`) does, for the same reason: approachable to a researcher, independent of the internal domain vocabulary.

`api/client.ts` opens `new EventSource` against `/api/query` (all parameters in the URL, native GET support); `fetchSymbols`/`fetchTraditions`/the `symbol`/`tradition` parameter names on `streamQuery` keep their pre-rename names, matching the API's own surface (see "API package" above). Component state accumulates per SSE event: `graphFacts`, `conceptCandidates[]`, `pairCandidates[]`, appended as events land — sections render as their data arrives, not after a single blocking fetch. `PassageCard` renders source attribution (`source.citation_label || `${source.title}, ${source.author}``, plus `, {locator}` when present — matching `cli/formatting.py`'s own attribution formula) and score only, never passage text (FR4).

`SignTraditionPicker` (renamed from `SymbolTraditionPicker`) adds a semiotic-system `<select>` ahead of the sign selector (FR20): its options are the distinct `semiotic_system` values across the fetched `SignSummary[]` (no separate endpoint — `/api/symbols` already carries what's needed), sorted; choosing one filters which signs the sign `<select>` offers, exactly as choosing a sign already filters which traditions the tradition `<select>` offers. Changing the system resets both the sign and tradition selections, the same way changing the sign already resets the tradition selection.

`GraphFactsPanel` renders the queried sign's own `properties`, the manifestation's own `properties`, the manifestation's `interpretants`, then each intersemiotic interpretant — and for each one, the target sign's own `properties` and the interpretant's `target_interpretants` nested under the correspondence line (FR16). The target of a correspondence carries facts of its own (e.g. The Sun's `hebrew_letter` correspondence to Qoph brings in Qoph's `numeric_value`/`meaning` properties and `foundation`/`constellation` interpretants), not just the bare relationship claim.

`App.tsx` tracks which concept(s) a selected passage came from (`selectedConcepts: string[]`) alongside `selectedPassage` — a per-concept section passes `[candidates.concept]`, a pair section passes `pair.concepts` — so `PassageDetailPanel` knows what to scope an AI Summary request to (FR17). `PassageDetailPanel` is rendered with `key={selectedPassage?.chunk_id}` so React remounts it fresh on every new selection, resetting its internal summary/loading/error state rather than carrying a stale summary over to the next passage.

`PassageDetailPanel` (FR5, FR17-FR19) orders its content metadata-first: the `Source`/`Locator`/`Score` `<dl>` above the passage text (no `Tradition` row — `RetrievedPassage` carries none), so the citation is visible without scrolling past the passage. Below the text, an "AI Summary — {concepts}" button calls `api/client.ts::summarizePassage(text, concepts)` (`POST /api/summarize`) and renders the returned summary, or a client-visible error on failure (FR19), without touching the rest of the displayed query result. `.passage-detail` is bounded to `max-height: calc(100svh - 2rem)` with `overflow-y: auto` so a long passage scrolls inside the panel instead of extending past the viewport with no way to reach the rest of it.

## Dev/prod serving

- Dev: `uv run uvicorn mythrix.api.app:app --reload` (port 8000) + `cd web && npm run dev` (Vite, port 5173). `CORSMiddleware` allows the Vite origin. `VITE_API_BASE_URL` is always absolute.
- Prod: FastAPI serves the built `web/dist` via `StaticFiles`, single process, no CORS.
