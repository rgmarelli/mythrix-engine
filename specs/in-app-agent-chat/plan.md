# In-App Agent Chat — plan

## Context

`spec.md` commits v0 to a docked chat panel grounded in the active hotspot,
backed by the existing `mythrix-agent` LangGraph tool-calling loop (currently
CLI-only), reusing all 7 existing read-only tools with no new tools, replacing
the standalone "Generate AI summary" button. The two constraints from ADR 0006
that shape everything below: the generation model may orchestrate but never
retrieve/interpret directly, and it runs on a local Ollama model only. The
agent stack (`agent/runner.py`, `agent/graph.py`, `agent/tools.py`,
`agent/cli.py`) already exists and is fully tested against a CLI surface; this
plan exposes it through `POST /api/agent` with per-session conversation +
context state, and builds the panel against it. Nothing in `core/` changes —
this is purely an `agent/`, `api/`, and `web/` feature.

## Architecture

### Backend turn loop

`agent/runner.py::run_turn` stays the low-level LangGraph-driving primitive,
extended with one new optional parameter, `context_summary: str = ""`
(defaulted so `agent/cli.py::run_agent`'s existing call site is untouched).
`agent/graph.py`'s `AgentState` gains one new plain (non-`add_messages`) key,
`context_summary: str` — last-write-wins, never rewritten mid-turn since no
node in v0 writes it. `agent_node` reads it and folds it into the model
invocation before the existing `SYSTEM_PROMPT`-based call — this mirrors the
*existing* pattern exactly: `SYSTEM_PROMPT` is already built fresh per call and
never persisted into `state["messages"]`, so this extends a pattern already in
place rather than introducing a new one.

A new orchestration module, `agent/turn_service.py`, composes one full API
turn:

1. Look up (or create) this `session_id`'s stored `SessionState` (history +
   `AgentContext`).
2. Detect thread reset by comparing incoming `ui_selection` against the stored
   context's `region_id` and session-scoped fields. If triggered, clear
   `agent_notes` now, before anything else (FR3).
3. Render `context_summary` text from the (possibly-just-reset) context.
4. Call `run_turn(graph, history, message, context_summary=..., max_tool_iterations=...)`.
5. Scan the newly appended messages for `ToolMessage`s: backfill session/
   thread-scoped context fields deterministically from tool results
   (mapping below), and build structured cards from the same tool results.
6. Split `agent_notes` out of the raw reply text (`agent/notes.py`); validate
   citation markers against the turn's accumulated valid-id set; strip all
   marker tokens (valid or not) from the visible text regardless of outcome,
   since Non-goals forbid visible `[G#]`/`[S#]` syntax.
7. Persist updated `SessionState`; return the three-part response.

`api/routes.py`'s new handler stays thin — dependency wiring plus one call
into `run_chat_turn(...)`, matching every existing route's thinness (e.g.
`/api/summarize`).

### Session/context storage

New `agent/sessions.py`: `SessionState` (dataclass: `history: list`,
`context: AgentContext`) and `SessionStore` (in-memory
`dict[str, SessionState]`, plus a per-session lock for double-submit safety).
Instantiated once in `app.py`'s `lifespan`, stashed at
`app.state.agent_sessions` — cheap and never fails, so unlike the agent graph
(below) it belongs at startup. Matches FR14 (process-lifetime only, no
cross-restart persistence) exactly, since nothing here touches disk. Keyed by
a client-generated `session_id` (`crypto.randomUUID()`, lazily created once
per mount inside the new panel component — no persistence beyond the page's
lifetime). A per-session lock guards double-submit; the frontend disabling
its composer while awaiting a reply (mirroring the app's existing `isQuerying`
pattern) is the primary defense, the lock is cheap insurance on top.

### Three-part response contract (concrete shapes, `api/routes.py`)

```python
class AgentUiSelection(BaseModel):          # what the browser sends, as-is, each turn
    semiotic_system: str | None = None
    sign: str | None = None
    tradition: str | None = None
    source_id: str | None = None            # facet
    interpretant: str | None = None         # facet
    min_score: float | None = None
    region_id: str | None = None            # active hotspot; None = no hotspot selected

class AgentTurnRequest(BaseModel):
    session_id: str
    message: str
    ui_selection: AgentUiSelection

class AgentContext(BaseModel):              # same shape as AgentUiSelection, backend-confirmed
    semiotic_system: str | None = None
    sign: str | None = None
    tradition: str | None = None
    source_id: str | None = None
    interpretant: str | None = None
    min_score: float | None = None
    region_id: str | None = None
    # agent_notes is deliberately NOT here — backend/agent working memory only,
    # never round-tripped to the client (the context strip only needs the
    # hotspot reference + interpretants, which the frontend already has).

class AgentCard(BaseModel):                 # discriminated by `type`
    type: Literal["citation", "interpretant_chips"]
    # citation: source_label, locator, text
    # interpretant_chips: chips[]

class AgentTurnResponse(BaseModel):
    context: AgentContext
    reply_text: str
    cards: list[AgentCard]
    instructions: list[dict] = []           # always [] in v0; v1 defines variants
    thread_reset: bool
```

The frontend renders the "— now reading {reference} —" divider itself from
data it already has (`selectedHotspot`) when `thread_reset` is `true` — the
backend doesn't render that string.

## Affected modules

**`src/mythrix/agent/runner.py`** — add `context_summary: str = ""` param to
`run_turn`, seeded into the initial `graph.stream(...)` state dict. Remove the
two stray `print(last_message)` / `print("---")` debug lines (current lines
46-47) — CLI-debugging leftovers that would spam server stdout on every
LangGraph step in a server process.

**`src/mythrix/agent/graph.py`**:
- `AgentState` gains the `context_summary: str` key described above.
- `agent_node` reads `state.get("context_summary", "")` and folds it into the
  model invocation alongside the existing `SYSTEM_PROMPT`.
- Generalize `route_after_tools`/`clarify_tradition_node` (FR6): replace the
  `last_message.name == "get_symbol"` / `payload.get("needs_tradition")`
  hardcoding with a generic rule — any `ToolMessage` whose JSON payload
  contains a truthy `needs_*` key routes to one generic `clarify_node`, which
  reads whichever key is present and composes the question from that
  payload's own fields. Same deterministic, zero-model-call bypass, just
  de-hardcoded from one tool/key name. `get_symbol`'s `needs_tradition`
  becomes the first case exercised through the generic path — no behavior
  change for it.
  - **Decided scope**: this generalizes the *mechanism* only. Semiotic-system-
    level ambiguity (named in `spec.md`'s Context-object text) stays on master
    FR62's existing softer, prompted path — the system prompt already says
    "if none is specified and multiple systems exist, ask the user to choose
    one." `get_symbol`/`list_symbols` are not gaining a `semiotic_system`
    parameter or a `needs_semiotic_system` sentinel in this pass.
- `tests/unit/test_agent_graph.py` needs corresponding renames
  (`route_after_tools`/`clarify_tradition_node` → generic names).

**`src/mythrix/agent/tools.py`** — no changes for v0 (FR9: no new tools).

**`src/mythrix/agent/prompts.py`** — two additions to `SYSTEM_PROMPT`, both
needing empirical tuning against the real local model:
1. A `[G#]`/`[S#]` marker-emission convention for FR11. Confirmed by reading
   the current prompt: it has **no** marker-emission instruction today (only
   "preserve citations and locators returned by tools") — the `[G#]`/`[S#]`
   convention exists solely in the *retired* `synthesis/prompts.py` prompt,
   which the agent doesn't use. This is new prompt-writing, not wiring.
2. The `agent_notes` fenced-block convention (a prompt-level instruction only
   — no new tool/node).

**New `src/mythrix/agent/context.py`** — `AgentContext`,
`detect_thread_reset(previous, incoming_ui_selection) -> bool`,
`backfill_from_tool_results(context, new_messages) -> AgentContext`,
`render_context_summary(context) -> str`.

Deterministic backfill mapping: `get_symbol` (no `needs_tradition`) → `sign`
(canonical name from result), `tradition` (from the call's own arg / result
field); `query_symbol` → same two, plus facet hints if queried with an
explicit source/interpretant; `list_traditions`/`list_symbols`/
`list_semiotic_systems` → never backfill (discovery only); `fetch_segments`/
`summarize_passage` → never backfill sign/tradition (operate on coordinates/
text, not sign identity). Fully code-driven, no model involvement — consistent
with ADR 0006.

**New `src/mythrix/agent/sessions.py`** — `SessionState`, `SessionStore` (above).

**New `src/mythrix/agent/cards.py`** — `build_cards(tool_name, payload) -> list[dict]`.
`query_symbol`'s `regions[].segments[]` → citation cards (verbatim text +
locator); `regions[].matches[]` → an interpretant-chips card; `fetch_segments`'s
list → citation cards; `get_symbol`'s `citations` array → a lighter
attribution-only rendering (structural graph citations, not retrieved corpus
text — don't force into the same citation-card shape as `query_symbol`'s output).

**New `src/mythrix/agent/notes.py`** — `split_agent_notes(reply_text) -> tuple[str, str]`,
the fenced-block parser. Order: extract/strip the notes block *first*
(producing `visible_reply`), then run marker validation only against
`visible_reply` — the notes block shouldn't itself carry citation markers,
keeping the two concerns cleanly separated.

**New `src/mythrix/agent/turn_service.py`** — `run_chat_turn(...)`,
orchestrator described above; owns marker-validation-then-stripping order and
the failure-mode handling below.

**`src/mythrix/core/synthesis/citations.py`** — add
`find_invalid_markers(text: str, valid_ids: set[str]) -> tuple[str, ...]`,
extracting the two-line body currently inline in `validate_citations`; keep
`validate_citations` as a thin wrapper
(`find_invalid_markers(text, set(graph_fact_ids(...)) | set(passage_ids(...)))`)
for any existing/future typed-object caller. Chosen over threading typed
`GraphFacts`/`RetrievedPassage` objects through the tool layer, because
`tools.py` only ever produces flattened dicts — `turn_service.py` builds
`valid_ids` directly from those dicts each turn.

**Decided (failure mode)**: on a citation-validation failure, treat it like a
tool failure (FR12) — catch `CitationValidationError` internally in
`turn_service.py`, discard the reply, show a distinct in-thread fallback
message, session continues. `core/errors.py`'s `CitationValidationError`
(already defined, unused, built for exactly this) becomes a real internal
control-flow signal rather than dead code, without turning a soft grounding
failure into a hard 500 — it is not propagated to the FastAPI exception handler.

**`src/mythrix/api/app.py`** — `lifespan` gains
`app.state.agent_sessions = SessionStore()` (cheap, always built) and
`app.state.agent_graph = None` (deliberately *not* built eagerly — see below).

**`src/mythrix/api/dependencies.py`** — add `get_agent_sessions(request) -> SessionStore`
(trivial, like `get_stores`) and `get_agent_graph(request) -> CompiledStateGraph`
implementing a third dependency pattern, distinct from the two existing ones:
lazy-build-once-then-cache. `build_agent_graph` calls `_build_tool_chat_model`
with `validate_model_on_init=True` — fail-fast against a live Ollama daemon.
Building it unconditionally at `lifespan` (like `get_stores`) would make the
entire API server fail to start for any deployment with no agent/generation
model configured, which `get_chat_client`'s own docstring says is the common
case. Instead: `get_agent_graph` builds on first request only, caches the
result on `app.state.agent_graph`, and a build failure surfaces as the same
502 `MythrixError` response `/api/summarize` already produces for an
unconfigured model — just on first chat turn rather than at server startup.

**`src/mythrix/api/routes.py`** — new `POST /api/agent`, models per
Architecture above, `Depends(get_agent_sessions)` + `Depends(get_agent_graph)`,
delegating to `turn_service.run_chat_turn(...)`. CORS needs no change (already
allows POST).

**`web/src/App.tsx`** — mount `AgentChatPanel` as a direct sibling under
`<div className="app">` (not nested in `.results-grid`/`HotspotDetailPanel`,
which doesn't receive the full selection state today and shouldn't be made to
for this), passing the current-selection bundle (`selectedSystem`,
`selectedSymbol`, `selectedTradition`, `minScore`, `selectedSourceId`,
`selectedInterpretant`, `selectedRegionId`) plus `selectedHotspot` (for
client-side context-strip/reset-divider rendering, since hotspot reference +
interpretants are already fully known client-side). Renders unconditionally
regardless of `queryResult`, since fixed/floating positioning is independent
of the rest of the layout.

**`web/src/components/HotspotDetailPanel.tsx`** — remove `summary`/
`isSummarizing`/`summaryError` state (current lines 36-38), `handleSummarize`
(136-147), the `ai-summary-button` (185-187), the summary/error render block
(213-219), and the now-unused `summarizePassage` import.

**`web/src/api/client.ts` / `web/src/api/types.ts`** — remove `summarizePassage`
(no remaining caller); add `postAgentTurn` following the fuller wire-type/
view-model/seam-function convention already established by `toHotspot()` (not
the inline-typed shortcut `/api/summarize` used) — new wire types
(`AgentTurnRequestWire`/`AgentContextWire`/`AgentCardWire`) and view-model
types, translated in one function in `client.ts`.

**`web/src/index.css`** — append a new, clearly delimited `.agent-dock`
section defining the spec's custom properties scoped to that subtree only
(not `:root`), plus the panel's fixed bottom-right layout. First
`position: fixed` / z-indexed rule in the codebase — pick and document a
z-index value, and manually check visual coexistence with `.hotspot-detail`'s
existing `position: sticky` + `max-height: calc(100svh - 2rem)` at common
viewport sizes.

**New `web/src/components/AgentChatPanel.tsx`** (+ small sub-components for
message bubble / citation card / interpretant chips / reset divider, left to
`tasks.md`) — owns collapse state, composer, `sessionId` (lazy
`useState(() => crypto.randomUUID())`), and the `postAgentTurn` call.

## Data flow

**Normal turn (no reset, no ambiguity).** User types in the composer;
`AgentChatPanel` calls `postAgentTurn(sessionId, message, currentUiSelection)`.
The route handler resolves `SessionState` via `get_agent_sessions`, resolves
the lazily-cached graph via `get_agent_graph`, calls
`turn_service.run_chat_turn`. `detect_thread_reset` compares the incoming
`region_id` and session-scoped fields against the stored context — no change,
no reset. `render_context_summary` produces something like "Active hotspot:
Genesis 1:1-5 in tarot/rider-waite; sign: The Tower." `run_turn` streams the
graph with this as `context_summary`; the model calls `query_symbol`, gets a
normal region-list dict back, composes a reply (with `[G#]`/`[S#]` markers per
the new prompt convention). `backfill_from_tool_results` confirms `sign`/
`tradition` unchanged. `build_cards` turns the region's segments/matches into
citation + interpretant-chip cards. Marker validation passes; markers are
stripped from `reply_text` regardless. Response: updated (unchanged) context,
reply text, cards, `thread_reset: false`.

**Thread-reset case.** User navigates to a new hotspot in the top viewer.
`App.tsx`'s `selectedRegionId` changes; the next chat turn's
`ui_selection.region_id` differs from what's stored in
`SessionState.context.region_id`. `detect_thread_reset` returns `true` before
the agent loop runs (FR3); `turn_service` clears `context.agent_notes` and
`session.history` right then, keeps session-scoped fields untouched, updates
`context.region_id` to the new value, and then invokes the loop with an empty
history and a `context_summary` reflecting only the new hotspot (no stale
`agent_notes` leak, and no stale transcript for the model to imitate).
Response carries `thread_reset: true`; the panel renders the reset divider
from its own already-known `selectedHotspot` data. A second, subtler reset
path: if the model itself resolves a different sign/tradition than what was
stored (agent-driven, chat-only), `turn_service` compares the tool-trace-derived
session-scoped fields against the pre-turn stored values after the loop
finishes, and clears `agent_notes` and `session.history` as part of finalizing
that turn's context if they differ.

**Ambiguity-clarification case.** User asks about a sign with more than one
tradition without naming one. The model calls `get_symbol(symbol=X)`;
`_resolve_sign` finds it, the tool returns
`{"needs_tradition": True, "symbol": ..., "traditions": [...]}`. The
generalized `route_after_tools` detects the truthy `needs_*` key and routes to
the generic `clarify_node` — the model is never invoked again this turn. The
composed question is returned as `reply_text` verbatim (no cards, since
nothing was retrieved). `backfill_from_tool_results` leaves `tradition`
unset. Next turn, the user names a tradition; the model calls `get_symbol`
again with both `symbol` and `tradition`, gets real facts back, and
`backfill_from_tool_results` writes `context.tradition` from the tool's own
resolved args/result.

## Verification

**Manual, end-to-end (primary — no new frontend test infra for v0):** run the
`mythrix-agent` CLI unchanged first to confirm no regression from the
`AgentState`/`context_summary` addition; then run the API + web dev servers
together and exercise: (a) a normal grounded question against an active
hotspot — citation/chip cards render, no bracket markers leak into visible
text; (b) a hotspot-navigation-triggered reset — the reset divider appears and
a prior `agent_notes` reference is not remembered after reset; (c) an
ambiguous-tradition question — the deterministic clarification question
appears with no model latency; (d) an unconfigured/unreachable Ollama model —
the lazy `get_agent_graph` failure surfaces as a clear 502 on the first chat
turn rather than crashing the server at boot; (e) rapid double-submit on the
composer — the disabled-while-awaiting-reply UX plus session lock prevent any
corrupted turn ordering.

**Automated (backend, following existing patterns exactly — no new test
tooling needed):** unit tests for `detect_thread_reset` (region change /
session-scope change / no change), `backfill_from_tool_results` (one case per
relevant tool), `find_invalid_markers`, `split_agent_notes`, the generalized
`route_after_tools`/`clarify_node`, and a `test_api.py`-style integration test
for `POST /api/agent` covering a full turn plus the reset and clarification
cases, via `app.dependency_overrides[get_agent_sessions]`/`[get_agent_graph]`
(the exact pattern `test_api.py` already uses for `get_stores`/`get_chat_client`).
