# In-App Agent Chat — Tasks

Ordered so each backend layer is testable before the next depends on it, and
before the frontend consumes any of it. Backend core/graph changes first
(T1–T3), then the new orchestration modules (T4–T9), then API wiring
(T10–T13), then backend tests (T14), then frontend (T15–T21), then
verification (T22–T23).

## Backend — agent core

- [x] **T1 — `runner.py`: `context_summary` param + remove debug prints.**
  Add `context_summary: str = ""` to `run_turn` (default keeps
  `agent/cli.py::run_agent`'s existing call site untouched), seeded into the
  initial `graph.stream(...)` state dict alongside `messages`. Remove the two
  stray `print(last_message)` / `print("---")` lines (current lines 46-47).

- [x] **T2 — `graph.py`: `context_summary` state key + `agent_node` wiring.**
  Add `context_summary: str` to `AgentState` (plain key, not
  `add_messages`). `agent_node` reads `state.get("context_summary", "")` and
  folds it into the model invocation alongside the existing `SYSTEM_PROMPT`
  (prepended as part of the same `SystemMessage`, not persisted into
  `state["messages"]` — mirrors how `SYSTEM_PROMPT` itself is already
  handled).

- [x] **T3 — Generalize `route_after_tools`/`clarify_tradition_node` to any `needs_*` key.**
  Replace the `last_message.name == "get_symbol"` /
  `payload.get("needs_tradition")` hardcoding with a generic rule: any
  `ToolMessage` whose JSON payload contains a truthy key starting with
  `needs_` routes to one generic `clarify_node`, which reads whichever key is
  present and composes the question from that payload's own fields (symbol +
  the value list under the matching key). `get_symbol`'s `needs_tradition`
  becomes the first case exercised through the generic path — no behavior
  change for it. Rename `clarify_tradition_node` → `clarify_node` and the
  `"clarify_tradition"` graph node name → `"clarify"` throughout
  `compile_agent_graph`. **Decided scope**: this generalizes the mechanism
  only — semiotic-system-level ambiguity stays on master FR62's existing
  softer, prompted path; `get_symbol`/`list_symbols` are not gaining a
  `semiotic_system` parameter or a `needs_semiotic_system` sentinel here.
  Update `tests/unit/test_agent_graph.py`'s imports/names to match
  (`clarify_tradition_node` → `clarify_node`, `"clarify_tradition"` →
  `"clarify"`).

## Backend — new orchestration modules

- [x] **T4 — `agent/prompts.py`: marker + `agent_notes` conventions.**
  Add to `SYSTEM_PROMPT`: (1) a `[G#]`/`[S#]` marker-emission instruction
  (the prompt currently has none — only "preserve citations and locators
  returned by tools"; the existing `[G#]`/`[S#]` convention lives only in the
  retired `synthesis/prompts.py`, unused by the agent); (2) an `agent_notes`
  fenced-block convention for the model to record its own working notes
  (e.g. "already summarized this passage") separately from its visible
  reply. Both need empirical tuning against the real local model during
  manual verification (T22) — flag this task for a follow-up prompt pass if
  the first wording doesn't hold up live.

- [x] **T5 — New `core/synthesis/citations.py::find_invalid_markers`.**
  Extract the two-line body currently inline in `validate_citations` into
  `find_invalid_markers(text: str, valid_ids: set[str]) -> tuple[str, ...]`.
  Keep `validate_citations` as a thin wrapper
  (`find_invalid_markers(text, set(graph_fact_ids(...)) | set(passage_ids(...)))`)
  — no behavior change for its existing callers/tests.

- [x] **T6 — New `agent/context.py`.**
  Define `AgentContext` (the single shape reused both as `turn_service`'s
  internal working context and as `api/routes.py`'s response field — same
  fields as `AgentUiSelection` minus `agent_notes`, which is never
  round-tripped to the client per plan.md), plus `agent_notes: str` carried
  alongside it in `SessionState` (T8), not on the wire type itself.
  Implement:
  - `detect_thread_reset(previous: AgentContext, incoming: AgentUiSelection) -> bool`
    — `True` if `incoming.region_id` differs from `previous.region_id`, or
    if any session-scoped field (`semiotic_system`, `sign`, `tradition`)
    differs.
  - `backfill_from_tool_results(context: AgentContext, new_messages: list) -> AgentContext`
    — scans the turn's new `ToolMessage`s and deterministically fills
    unset/changed `sign`/`tradition` (and facet hints where applicable) per
    the mapping in plan.md: `get_symbol` (no `needs_tradition`) →
    `sign`/`tradition`; `query_symbol` → same two, plus facet hints when
    queried with an explicit source/interpretant; `list_traditions`/
    `list_symbols`/`list_semiotic_systems` → never backfill (discovery
    only); `fetch_segments`/`summarize_passage` → never backfill sign/
    tradition. No model involvement.
  - `render_context_summary(context: AgentContext) -> str` — the compact
    text folded into `context_summary` (T2), e.g. "Active hotspot: {region};
    sign: {sign} ({tradition})."

- [x] **T7 — New `agent/sessions.py`.**
  `SessionState` (dataclass: `history: list`, `context: AgentContext`,
  `agent_notes: str`). `SessionStore`: in-memory `dict[str, SessionState]`
  plus a per-session `threading.Lock` (or `asyncio.Lock`, matching the route
  handler's sync/async shape) for double-submit safety. No disk I/O — matches
  FR14 (process-lifetime only).

- [x] **T8 — New `agent/cards.py::build_cards`.**
  `build_cards(tool_name: str, payload: dict) -> list[dict]`. Mapping:
  `query_symbol`'s `regions[].segments[]` → citation cards (verbatim text +
  locator); `regions[].matches[]` → one interpretant-chips card;
  `fetch_segments`'s list → citation cards; `get_symbol`'s `citations` array
  → a lighter attribution-only card shape (not forced into the citation-card
  shape, per plan.md — it's structural graph citation, not retrieved corpus
  text). Every other tool → `[]`.

- [x] **T9 — New `agent/notes.py::split_agent_notes`.**
  `split_agent_notes(reply_text: str) -> tuple[str, str]` — extracts and
  strips the `agent_notes` fenced block first (per T4's convention),
  returning `(visible_reply, notes)`. Marker validation (T5) runs only
  against `visible_reply`, never the notes block.

- [x] **T10 — New `agent/turn_service.py::run_chat_turn`.**
  Orchestrates one full turn, composing T1–T9:
  1. Look up (or create) the `session_id`'s `SessionState`.
  2. `detect_thread_reset(stored_context, ui_selection)`; if `True`, clear
     `agent_notes` now, before the agent loop runs (FR3).
  3. `render_context_summary` from the (possibly-just-reset) context.
  4. `run_turn(graph, history, message, context_summary=..., max_tool_iterations=...)`.
  5. `backfill_from_tool_results` from the newly appended `ToolMessage`s;
     `build_cards` from the same tool results. If the backfilled
     session-scoped fields differ from the pre-turn stored values (the
     "model-driven reset" case in plan.md's Data flow), clear `agent_notes`
     as part of finalizing this turn's context too.
  6. `split_agent_notes` on the raw reply; validate markers in
     `visible_reply` via `find_invalid_markers` against this turn's
     accumulated valid-id set (built from the tool-result dicts directly,
     not typed objects); strip all marker tokens (valid or not) from
     `visible_reply` regardless of validation outcome (Non-goals forbid
     visible marker syntax).
  7. On a `CitationValidationError` (raised internally when
     `find_invalid_markers` returns non-empty — **decided failure mode**:
     treated like a tool failure, FR12): discard the reply, return a
     distinct in-thread fallback message instead; the session continues;
     this is caught inside `run_chat_turn` and never propagates to the
     FastAPI exception handler.
  8. Persist updated `SessionState`; return the three-part response
     (`AgentContext`, `reply_text`, `cards`, `instructions=[]`,
     `thread_reset`).

## Backend — API wiring

- [x] **T11 — `api/app.py`: session store + lazy graph slot.**
  In `lifespan`, add `app.state.agent_sessions = SessionStore()` (cheap,
  built unconditionally, like `app.state.stores`) and
  `app.state.agent_graph = None` (deliberately not built eagerly).

- [x] **T12 — `api/dependencies.py`: `get_agent_sessions` + `get_agent_graph`.**
  `get_agent_sessions(request) -> SessionStore` — trivial, mirrors
  `get_stores`. `get_agent_graph(request) -> CompiledStateGraph` —
  lazy-build-once-then-cache on `app.state.agent_graph`: on first call,
  builds via `build_agent_graph(...)` / `build_tools(...)` /
  `_build_tool_chat_model(..., validate_model_on_init=True)` (fail-fast
  against a live Ollama daemon), caches the result; subsequent calls return
  the cached graph. A build failure raises the same `MythrixError` subclass
  `get_chat_client` already raises for an unconfigured/unreachable model, so
  the existing registered exception handler turns it into the same 502
  shape `/api/summarize` already produces — just surfacing on the first chat
  turn instead of at server startup.

- [x] **T13 — `api/routes.py`: `POST /api/agent`.**
  Add `AgentUiSelection`, `AgentTurnRequest`, `AgentCard`,
  `AgentTurnResponse` (importing `AgentContext` from `agent/context.py`, per
  T6) exactly as specified in plan.md's "Three-part response contract". New
  route handler, thin (dependency wiring + one call into
  `turn_service.run_chat_turn(...)`), matching `/api/summarize`'s existing
  thinness. No CORS change needed (POST already allowed).

## Backend — tests

- [x] **T14 — Backend unit + integration tests.**
  Following existing patterns exactly (no new test tooling):
  - `test_agent_runner.py`: `context_summary` is seeded into the graph's
    initial state (add a case alongside the existing tests); no behavior
    change when the param is omitted.
  - `test_agent_graph.py`: update renamed
    `clarify_tradition_node`/`"clarify_tradition"` references (T3); add a
    case proving the generic `needs_*` routing fires for a *different*
    tool/key than `get_symbol`/`needs_tradition`, to prove the mechanism is
    actually generalized and not just renamed.
  - New `test_agent_context.py`: `detect_thread_reset` (region change /
    session-scope field change / no change → `True`/`True`/`False`);
    `backfill_from_tool_results` (one case per tool in the mapping, T6);
    `render_context_summary` (basic shape).
  - New `test_agent_cards.py`: `build_cards` per tool (T8).
  - New `test_agent_notes.py`: `split_agent_notes` (T9) — with/without a
    notes block, notes block content excluded from `visible_reply`.
  - `test_citations.py` (existing file — check name): `find_invalid_markers`
    (T5) covers what `validate_citations`'s tests already implicitly cover;
    add a direct unit test for the extracted function.
  - New `test_agent_turn_service.py`: a full turn via `run_chat_turn` with a
    stub graph/tools — normal turn, thread-reset turn (region change),
    ambiguity-clarification turn, citation-validation-failure turn (T10
    step 7 fallback path).
  - `test_api.py`: new `POST /api/agent` tests via
    `app.dependency_overrides[get_agent_sessions]`/`[get_agent_graph]` (the
    exact pattern already used for `get_stores`/`get_chat_client`) —
    full-turn happy path, thread-reset response (`thread_reset: true` +
    cleared `agent_notes` reflected in the next turn), ambiguity
    clarification (no model latency — assert the stub model is never
    invoked a second time), and an unavailable-model 502 on first call to
    `get_agent_graph`.

## Frontend

- [x] **T15 — `api/types.ts`: agent wire + view-model types.**
  Add `AgentUiSelectionWire`, `AgentTurnRequestWire`, `AgentContextWire`,
  `AgentCardWire` (discriminated by `type`), `AgentTurnResponseWire`, plus
  view-model counterparts (`AgentContext`, `AgentCard`,
  `AgentTurnResult` — camelCase, matching the app's existing view-model
  naming convention from `Hotspot`/`HotspotSegment`).

- [x] **T16 — `api/client.ts`: `postAgentTurn`, remove `summarizePassage`.**
  Remove `summarizePassage` (no remaining caller after T18). Add
  `postAgentTurn(sessionId, message, uiSelection): Promise<AgentTurnResult>`
  following the fuller wire-type/view-model/seam-function convention
  `toHotspot()` already establishes (not `/api/summarize`'s inline-typed
  shortcut) — one translation function mapping the wire response onto the
  view model.

- [x] **T17 — `.agent-dock` design tokens + fixed layout in `index.css`.**
  Append a new, clearly delimited `.agent-dock` section: the custom
  properties from spec.md's Design tokens, scoped to `.agent-dock` only (not
  `:root`); fixed bottom-right 392×540px layout; a documented `z-index`
  value. Manually check visual coexistence with `.hotspot-detail`'s existing
  `position: sticky` + `max-height: calc(100svh - 2rem)` at common viewport
  sizes (part of T23's manual pass, not a separate check here).

- [x] **T18 — New `web/src/components/AgentChatPanel.tsx` (+ sub-components).**
  Owns: collapse state (open/collapsed, per spec.md's Placement & states);
  `sessionId` via lazy `useState(() => crypto.randomUUID())`; composer input
  + send (single input, no shortcut pills); the `postAgentTurn` call and
  in-flight/disabled state (mirrors `App.tsx`'s existing `isQuerying`
  pattern — the primary double-submit defense, per plan.md, backed by
  T7's session lock). Sub-components (message bubble, verse-citation card,
  interpretant chips, reset divider) as separate files or co-located, per
  what reads cleanest once written — not prescribed further here. Renders
  the "— now reading {reference} —" divider itself from `selectedHotspot`
  data already available client-side when the response's `thread_reset` is
  `true` (the backend does not render that string, per plan.md). Context
  strip (gold background) always shows the current hotspot reference +
  interpretants from client-side data, per FR2.

- [x] **T19 — Mount `AgentChatPanel` in `App.tsx`.**
  Mount as a direct sibling under `<div className="app">` (not nested in
  `.results-grid`/`HotspotDetailPanel`, which doesn't receive the full
  selection state today). Pass the current-selection bundle
  (`selectedSystem`, `selectedSymbol`, `selectedTradition`, `minScore`,
  `selectedSourceId`, `selectedInterpretant`, `selectedRegionId`) plus
  `selectedHotspot` (for client-side context-strip/reset-divider
  rendering). Renders unconditionally regardless of `queryResult`.

- [x] **T20 — Remove the AI-summary button from `HotspotDetailPanel.tsx`.**
  Remove `summary`/`isSummarizing`/`summaryError` state (current lines
  36-38), `handleSummarize` (136-147), the `ai-summary-button` (185-187),
  the summary/error render block (213-219), and the now-unused
  `summarizePassage` import. `Add Context` and its state are untouched.

- [x] **T21 — Remove the now-orphaned `.ai-summary-button`/`.ai-summary-box` CSS**, if any exists in `index.css` outside the button/box T20 removed from markup, and confirm nothing else references them.

## Verification

- [x] **T22 — Lint/format/tests.**
  `ruff check .`, `ruff format .`, run the Python test suite (T14); `oxlint`
  and `tsc -b` / `vite build` for the frontend.

- [x] **T23 — End-to-end manual check (`/run`).**
  Ran the `mythrix-agent` CLI (`qwen2.5:3b`) — tool call + reply printed,
  clean exit, no regression from the `AgentState`/`context_summary`
  addition. Ran the API (`uvicorn`) + Vite dev servers together, driven live
  in a browser against the real ingested `.mythrix/` dataset:
  (a) verified — a grounded question against an active hotspot (The Sun,
  Apocalypse 12:1-6) produced an AI bubble plus a real citation card built
  from `get_symbol`'s tool result, no bracket markers visible; (b) verified
  — selecting a different hotspot (Ecclesiasticus 30:8-12) updated the
  context strip immediately client-side, and the next chat turn correctly
  cleared the thread to a single reset divider + new turn, confirmed via
  screenshot; (c) verified — an ambiguous-tradition question ("tell me
  about death") returned the deterministic clarification listing both
  traditions in ~1.2s (one model call to pick `get_symbol`, then the
  zero-model-call `clarify` bypass), both via `curl` and unit/integration
  tests; (d) verified — pointing `MYTHRIX_AGENT_MODEL` at a nonexistent
  model left `/api/traditions` at 200 (no boot crash) while `/api/agent`
  consistently returned 502 with a clear detail message across repeated
  calls (no bad-graph caching); (e) verified in-browser — three rapid
  clicks on `send` produced exactly one user bubble, one reply, and one
  logged `POST /api/agent` server-side; (f) **partially verified** — the
  "Active hotspot" → `fetch_segments` prompt instruction (added during this
  pass; see below) was confirmed correct against `gemma4:12b` (calls
  `fetch_segments` with exactly the right `source_id`/ordinal args), but a
  full live round trip through `summarize_passage` to a final reply could
  not be completed in-session: `gemma4:12b` is CPU-bound and did not finish
  a 2-3 hop tool-calling turn within an 8-minute budget on this hardware,
  and the faster `qwen2.5:3b` does not reliably follow the instruction at
  all (calls no tool, or the wrong one). The orchestration itself (multi
  tool-call backfill, card-building, marker validation) is covered by
  `test_agent_turn_service.py`/`test_api.py` against stub models — what's
  unverified live is specifically small/fast-local-model reliability on
  this one instruction, a model-capability gap flagged for the deployer's
  choice of `agent_model`, not a code defect. (g) verified — collapsing and
  re-opening the panel left the thread pixel-for-pixel unchanged.

  **Finding acted on**: the original prompt gave the model no way to turn
  the "Active hotspot" context line into a `fetch_segments` call, so "this
  passage" grounding silently failed. Fixed by adding an explicit
  imperative instruction to `SYSTEM_PROMPT` (`agent/prompts.py`) naming the
  `source_id::start_ordinal-end_ordinal` format and requiring an immediate
  `fetch_segments` call with no clarifying question first. Verified against
  `gemma4:12b` after the fix; left in place as-is per T4's note that this
  needs ongoing empirical tuning per deployment.
