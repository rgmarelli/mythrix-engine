# Agent Operator — Tasks

Ordered so each layer is testable before the next consumes it: ADR + dependency
+ config (T1–T3), agent core bottom-up (T4–T8), CLI (T9–T10), cleanup (T11),
then verification (T12–T13). Read-only, local Ollama, CLI surface only.

## Groundwork

- [x] **T1 — ADR 0006.**
  Write `specs/architecture-decisions/0006-conversational-agent-orchestration-boundary.md`
  (Context → Decision → Consequences → Alternatives) and add its row to
  `specs/architecture-decisions/README.md`. Must exist before implementation.

- [x] **T2 — Dependency + agent console script.**
  Add `langgraph` to `[project.dependencies]` in `pyproject.toml`; add
  `mythrix-agent = "mythrix.agent.cli:app"` to `[project.scripts]` (leaving the
  existing `mythrix` entry untouched); `uv sync`. Confirm `langchain-core`
  (`@tool`, message types) resolves transitively; pin only if imports need it. Do
  not add `prompt_toolkit`.

- [x] **T3 — Config fields.**
  In `core/config.py::Settings`, add `agent_model: str | None = None` and
  `agent_max_tool_iterations: int = 8`. No other config changes.

## Agent package (`src/mythrix/agent/`)

- [x] **T4 — `prompts.py`.**
  Add `SYSTEM_PROMPT` enforcing spec FR5/FR6: tools for all knowledge-base
  facts; never invent symbols/interpretations; carry through citations/locators;
  don't drop list items; **scope by semiotic system** — before listing
  traditions/symbols or getting/querying a symbol, use the named system or, if
  ambiguous, call `list_semiotic_systems` and ask which one (reuse it once
  established; on `get_symbol`'s `needs_tradition`, ask which tradition); answer
  directly and concisely.

- [x] **T5 — `tools.py` (`build_tools`) + store method.**
  (a) Add read-only `KuzuGraphStore.list_semiotic_systems() -> tuple[str, ...]`
  (distinct `semiotic_system` over signs with a manifestation, ordered).
  (b) Implement the factory closing over `stores`, `settings`, `chat_client`,
  returning the **seven** read-only `@tool`s: `list_semiotic_systems`,
  `list_traditions(semiotic_system?)`, `list_symbols(semiotic_system?)`,
  `get_symbol(symbol, tradition?)` (→ `get_manifestation`, resolving/prompting on
  tradition via `list_signs`), `query_symbol` (→ `query_regions`), `fetch_segments`
  (→ `fetch_source_segments`), `summarize_passage` (→ `render_passage_summary_prompt`
  + `chat_client.invoke`). Each returns compact structured data with
  citations/locators. Catch `MythrixError` at the tool boundary and return a
  structured error string. Include `_render_regions(RegionQueryResult) -> dict`
  (mirrors `GET /api/query`) and `_render_graph_facts(GraphFacts) -> dict` (for
  `get_symbol`) helpers.

- [x] **T6 — `graph.py`.**
  `AgentState` (`messages: Annotated[list, add_messages]`); `compile_agent_graph(
  llm_with_tools, tools)` — `agent` node (`SystemMessage` prepended fresh each
  call) + `ToolNode`, `START→agent`, conditional `route_after_agent` (`tools` vs
  `END`), `tools→agent`. `build_agent_graph(*, generation_model, base_url,
  num_ctx, tools)` constructs the real tool-bound `ChatOllama` and calls
  `compile_agent_graph`. The turn bound (spec FR12) turned out to be a
  `recursion_limit` *runtime* config LangGraph takes at `stream`/`invoke` time,
  not a compile-time parameter — `runner.run_turn` supplies it per call instead
  of `build_agent_graph` taking `max_tool_iterations`. The small
  "not found"/"unreachable" error-mapping is duplicated into `graph.py`'s
  `_build_tool_chat_model` (not factored out of `core/synthesis/chain.py`), to
  keep `core/` untouched beyond `list_semiotic_systems`. `OllamaChatClient`
  stays unchanged for the summarize tool.

- [x] **T6b — Deterministic `needs_tradition` short-circuit (spec FR7).**
  Add `"symbol"` (canonical name) to `get_symbol`'s `needs_tradition` payload in
  `tools.py`. In `graph.py`: `route_after_tools(state)` — `"clarify_tradition"`
  when the last message is a `ToolMessage` named `get_symbol` whose JSON content
  has `needs_tradition: true`, else `"agent"`; `clarify_tradition_node(state)` —
  builds a deterministic `AIMessage` from the payload's `symbol`/`traditions`, no
  model call. Wire `tools → {agent, clarify_tradition}` (replacing the
  unconditional edge) and `clarify_tradition → END`. Motivated by a live,
  sampling-dependent failure: the model composed fabricated interpretive content
  after a tool result carrying none at all — not reliably reproducible, so not
  fixable by prompting alone; removes the model from this one decision instead.
  **Verified:** 6/6 identical, correct clarifying replies across `qwen2.5:3b`
  and `llama3.2:latest` on the exact repro ("Tell me about The Sun") — no
  longer sampling-dependent because the model is never invoked for this reply.

- [x] **T7 — `runner.py`.**
  `TurnResult(reply, tool_calls)` and `run_turn(graph, history, user_text, *,
  max_tool_iterations) -> (new_history, TurnResult)`: append `HumanMessage`,
  stream the graph, collect the ordered tool-name trace, return updated history +
  result. Terminal-free.

- [x] **T8 — Agent-core unit tests.**
  - `list_semiotic_systems`: distinct, ordered; excludes a system whose signs
    lack a manifestation (mirrors `list_signs`).
  - `tools.py`: each wrapper's shape against fake `Stores`/`ChatClient`;
    `query_symbol`/`fetch_segments`/`get_symbol` dict mapping incl.
    citations/locators; `list_symbols`/`list_traditions` scope by
    `semiotic_system`; `get_symbol` auto-resolves a single-tradition sign, returns
    `needs_tradition` for a multi-tradition sign, `error` for an unknown slug;
    `MythrixError` → structured error string (not raised); **read-only invariant:
    built tool-name set is exactly the seven tools**.
  - `graph.py`: stub tool-capable client scripts one `tool_calls` message then a
    plain answer → `ToolNode` runs `query_symbol`, loop ends at `END`;
    `route_after_agent` routing; recursion bound ends a runaway loop.
  - `runner.py`: `run_turn` returns the ordered trace and preserves history
    across two turns.

## CLI (in the agent package — no `mythrix` CLI changes)

- [x] **T9 — `src/mythrix/agent/cli.py` (own entrypoint).**
  The agent's own Typer `app` (`name="mythrix-agent"`). Testable `run_agent(*,
  graph, max_tool_iterations, read_line, write) -> int` core (injected graph + I/O
  callables; loops; prints tool trace + reply; returns exit code) plus a `main`
  command that builds `Settings`, `build_stores`, resolves
  `agent_model or generation_model`, constructs `OllamaChatClient` (fail-fast →
  clean error, spec FR8), `build_tools`, `build_agent_graph`, runs the REPL over
  stdlib `input()` (`exit`/`quit`/EOF ends). Does **not** import or modify
  `cli/main.py`.

- [x] **T10 — CLI test.**
  `run_agent` with a fake graph and injected I/O: scripted turns print trace +
  reply, `exit 0`; EOF with no input exits `0`. `main()`'s fail-fast path tested
  via `CliRunner` with `Settings` monkeypatched to an unset `generation_model`
  and a `tmp_path` store (no live Ollama/`.mythrix/` needed): clean `Error: ...`
  message, exit `1`. Confirmed `mythrix --help` still lists exactly
  `query`/`load-symbols`/`load-documents` and nothing agent-related (agent CLI
  is a separate script, spec FR13).

## Cleanup

- [x] **T11 — Remove `prueba2.py`.**
  Delete `src/mythrix/prueba2.py`.

## Verification

- [x] **T12 — Lint/format/tests.**
  `ruff check .`, `ruff format .`, `uv run pytest` (incl. the opt-in
  `@pytest.mark.requires_ollama` integration turn if Ollama is available).

- [x] **T13 — End-to-end manual check.**
  Run against a **copy** of the live `.mythrix/` store (the real one was locked
  by the user's already-running `uvicorn`/Vite dev servers — not disturbed) with
  real Ollama (`qwen2.5:3b`): `list the symbols` → `list_semiotic_systems` +
  `list_symbols` called, real signs/traditions returned → `tell me about The
  Magician` → `get_symbol` returned `needs_tradition` for `rider-waite`/
  `marseille` and the agent asked which → `rider-waite` → a tool was called and
  a cited reply produced. Confirmed: tool traces print, history carries across
  turns, no crash, clean `exit` (code 0), and `mythrix --help` / `mythrix query`
  are unchanged. **Observed model-quality gap** (not a code defect, matches
  plan.md's Risks): `qwen2.5:3b` answered "list the symbols" directly instead of
  asking which semiotic system first (spec FR5), and after the `needs_tradition`
  prompt it called `query_symbol` instead of re-calling `get_symbol` with
  `tradition="rider-waite"` — small-model tool-selection is imperfect; the
  `agent_model` override exists to swap in a stronger local model.
