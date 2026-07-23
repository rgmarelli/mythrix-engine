# Agent Operator — Plan

## Overview

Add a new, self-contained `src/mythrix/agent/` package with its own
`mythrix-agent` console script that runs a LangGraph tool-calling loop over
Mythrix's *existing* operations. The agent
is the "conversational agent layer" the master spec anticipates (`specs/spec.md`
Non-goals; FR11, FR12) and productionizes the scratch prototype
`src/mythrix/prueba2.py` (agent-node ↔ `ToolNode` loop, `ChatOllama` +
`bind_tools`, REPL) into a tested, dependency-injected module.

No retrieval, graph, embedding, or synthesis logic is reimplemented. Every tool
is a thin wrapper over an existing function:

| Tool | Wraps | Existing surface it mirrors |
|------|-------|-----------------------------|
| `list_semiotic_systems()` | `KuzuGraphStore.list_semiotic_systems` (new, small) | — (new discovery capability) |
| `list_traditions(semiotic_system?)` | `KuzuGraphStore.list_traditions` / `list_signs` | `GET /api/traditions` |
| `list_symbols(semiotic_system?)` | `KuzuGraphStore.list_signs` | `GET /api/symbols` |
| `get_symbol(symbol, tradition?)` | `KuzuGraphStore.get_manifestation` (+ `list_signs` to resolve tradition) | — (mirrors the graph-facts half of `GET /api/query`) |
| `query_symbol(symbol, tradition, top_k?, min_score?)` | `query_service.query_regions(...)` | `GET /api/query` |
| `fetch_segments(source_id, start_ordinal, end_ordinal)` | `query_service.fetch_source_segments(...)` | `GET /api/segments` |
| `summarize_passage(passage_text, concepts)` | `render_passage_summary_prompt` + `ChatClient.invoke` | `POST /api/summarize` |

The generation model (local Ollama) drives only conversation and tool selection,
plus the explicit `summarize_passage` tool. The retrieval a tool triggers is
embedding-only and unchanged (master FR29, FR11).

The agent package adds **nothing to `core/`** except one small, read-only store
method (below); every other tool wraps an existing function unchanged.
`get_symbol` and the `semiotic_system` scoping on the list tools are built by
composing existing methods (`get_manifestation`, `list_signs`) in the agent's own
tool layer — no change to existing store signatures.

### Store addition: `KuzuGraphStore.list_semiotic_systems` (core)

This is the one deliberate change inside `core/`. `SignSummary` already carries
`semiotic_system`, so the distinct set *could* be derived in the agent from
`list_signs()` — but a dedicated store method is put in core on purpose: it is a
general read-only catalog query (the top-level scope above traditions/signs), and
it is the natural backing for a future web/API semiotic-system picker
(a `GET /api/semiotic-systems` route alongside `/api/traditions` and
`/api/symbols`), not only the agent. Keeping it in the deterministic access layer
lets the web UI reuse it rather than each caller re-deriving it. The agent's
`list_semiotic_systems` tool then stays a thin wrapper.

```python
def list_semiotic_systems(self) -> tuple[str, ...]:
    """Every distinct semiotic system that has at least one manifested sign,
    ordered — the top-level scope a picker/agent offers before signs/traditions."""
    result = self._execute(
        "MATCH (s:Sign)-[:HAS_MANIFESTATION]->(:Manifestation) "
        "RETURN DISTINCT s.semiotic_system ORDER BY s.semiotic_system", {},
    )
    ...  # collect column 0
```

Consistent with `list_signs` (only signs that actually have a manifestation, so
a picker never offers a dead scope).

## Data flow

```
mythrix-agent (REPL)
  → build_stores(Settings())                    once, at startup
  → OllamaChatClient(generation_model=…)         once, at startup (fail fast if unreachable)
  → build_tools(stores, settings, chat_client)   closures capture the deps
  → build_agent_graph(chat_client, tools)        compiled LangGraph

per turn:
  user text → AgentState.messages
    → agent node: llm.bind_tools(tools).invoke(history)
       → tool_calls?  → ToolNode runs the wrapped service fn → back to agent
       → else         → END, assistant text returned
  → print tool trace + assistant reply; append to history
```

## Package layout: `src/mythrix/agent/`

Mirrors the CLI's testable-core / thin-wrapper split so unit tests inject fakes
with no Ollama, Kùzu, or Chroma running.

### `tools.py` — `build_tools(stores, settings, chat_client) -> list`

A factory that closes over the already-built `Stores`
(`core/bootstrap.py::build_stores`), `Settings`, and a `ChatClient`, returning a
list of LangGraph `@tool`-decorated callables. Closures replace prueba2's
module-level globals so the tool set is constructed per session and is trivially
testable.

Each tool returns compact, structured, JSON-serializable data (dicts / lists of
dicts) carrying ids, names, locators, scores, verbatim text, and citation
markers — never prose — so the model relays cited evidence rather than inventing
it (spec FR6). Sketch:

```python
def build_tools(stores, settings, chat_client) -> list:
    @tool
    def list_semiotic_systems() -> list[str]:
        """List the available semiotic systems (top-level symbol domains).
        Ask the user which one to use before listing symbols/traditions when it is ambiguous."""
        return list(stores.graph_store.list_semiotic_systems())

    @tool
    def list_traditions(semiotic_system: str | None = None) -> list[dict]:
        """List available traditions. If semiotic_system is given, only traditions
        that have at least one sign in that system."""
        if semiotic_system is None:
            return [ {"slug": t.slug, "name": t.name} for t in stores.graph_store.list_traditions() ]
        slugs = {ts for s in stores.graph_store.list_signs()
                 if s.semiotic_system == semiotic_system for ts in s.tradition_slugs}
        return [ {"slug": t.slug, "name": t.name}
                 for t in stores.graph_store.list_traditions() if t.slug in slugs ]

    @tool
    def list_symbols(semiotic_system: str | None = None) -> list[dict]:
        """List available signs (symbols), optionally scoped to one semiotic system."""
        return [ {"slug": s.slug, "name": s.canonical_name,
                  "semiotic_system": s.semiotic_system, "traditions": list(s.tradition_slugs)}
                 for s in stores.graph_store.list_signs()
                 if semiotic_system is None or s.semiotic_system == semiotic_system ]

    @tool
    def get_symbol(symbol: str, tradition: str | None = None) -> dict:
        """Retrieve one named sign's facts (e.g. "the-magician"): its canonical name,
        semiotic system, properties, and — for a tradition — its interpretants,
        denotation, correspondences, and citations. Graph facts only, no corpus search.
        If the sign has one tradition, it is used; if several and none is given,
        return the choices and ask which tradition."""
        summary = next((s for s in stores.graph_store.list_signs() if s.slug == symbol), None)
        if summary is None:
            return {"error": f"unknown symbol '{symbol}'"}
        if tradition is None:
            if len(summary.tradition_slugs) == 1:
                tradition = summary.tradition_slugs[0]
            else:
                return {"needs_tradition": True, "traditions": list(summary.tradition_slugs)}
        facts = stores.graph_store.get_manifestation(symbol, tradition)   # GraphFacts
        return _render_graph_facts(facts)     # compact dict: sign, interpretants, citations, correspondences

    @tool
    def query_symbol(symbol: str, tradition: str,
                     top_k: int | None = None, min_score: float | None = None) -> dict:
        """Retrieve ranked evidence regions (hotspots) for a sign in a tradition.
        Returns each region's matched interpretants, verbatim segment text, and citation."""
        result = query_regions(
            symbol=symbol, tradition=tradition,
            graph_store=stores.graph_store, vector_store=stores.vector_store,
            embedder=stores.embedder,
            top_k=top_k or settings.retrieval_top_k,
            match_pool_size=settings.retrieval_match_pool_size,
            merge_top_k=settings.merge_top_k,
            min_score=min_score if min_score is not None else settings.retrieval_min_score,
            region_window_size=settings.region_window_size,
            region_min_interpretants=settings.region_min_interpretants,
        )
        return _render_regions(result)      # compact dict with citations, mirrors GET /api/query

    @tool
    def fetch_segments(source_id: str, start_ordinal: int, end_ordinal: int) -> list[dict]:
        """Read a contiguous ordinal range of one source's segments verbatim (no similarity search)."""
        segs = fetch_source_segments(source_id=source_id, start_ordinal=start_ordinal,
                                     end_ordinal=end_ordinal,
                                     graph_store=stores.graph_store, vector_store=stores.vector_store)
        return [ {"ordinal": s.ordinal, "locator": s.locator, "section": s.section, "text": s.text} for s in segs ]

    @tool
    def summarize_passage(passage_text: str, concepts: list[str]) -> str:
        """Summarize an already-retrieved passage, scoped to the given interpretants."""
        return chat_client.invoke(render_passage_summary_prompt(passage_text, tuple(concepts)))

    return [list_semiotic_systems, list_traditions, list_symbols, get_symbol,
            query_symbol, fetch_segments, summarize_passage]
```

Read-only by construction (spec FR4): no `upsert_*`, `load_*`, or reload function
is referenced anywhere in this module. This is a structural guarantee — a unit
test asserts the tool-name set is exactly the seven above.

`_render_graph_facts(GraphFacts) -> dict` renders one sign+manifestation compactly
(canonical name, semiotic system, interpretant values, denotation, correspondence
targets, and citation locators), reusing the same `GraphFacts` the query path
already builds — the `get_symbol` counterpart to `_render_regions`.

`MythrixError` raised inside a tool (unknown sign/tradition/source, unreachable
model) is caught at the tool boundary and returned to the model as a structured
error string, so a bad tool call becomes a recoverable turn rather than a crash
(spec FR11). `ToolNode` already surfaces tool exceptions back into the message
stream; we convert `MythrixError` specifically to a clean, model-readable message.

### `prompts.py` — `SYSTEM_PROMPT`

The operator system prompt. Enforces spec FR5/FR6:

- Use tools for every knowledge-base fact; never state a symbol, interpretant,
  source, or passage not present in a tool result.
- Never invent or infer interpretations; carry through the citation/locator each
  tool returns.
- When a tool returns a list, do not drop items.
- **Scope by semiotic system (spec FR5):** before listing traditions/symbols or
  getting/querying a symbol, determine the semiotic system. If the user named it,
  use it; if not and more than one exists, call `list_semiotic_systems` and ask
  the user which one — do not guess or list across all systems. Once established
  in the conversation, reuse it without re-asking. Likewise, if `get_symbol`
  reports `needs_tradition`, present the returned traditions and ask which one.
- Answer the user's request directly and concisely (matches `CLAUDE.md`).

(Distinct from `core/synthesis/prompts.py`, which renders passage-summary prompts
and `[G#]`/`[S#]` citation blocks; that module is reused unchanged by the
`summarize_passage` tool.)

### `graph.py` — the LangGraph state machine

Productionizes prueba2's graph. Split into two functions so a test can inject a
stub tool-calling model with no live Ollama:

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

def compile_agent_graph(llm_with_tools, tools: list) -> CompiledStateGraph:
    def agent_node(state): ...   # prepend SystemMessage, invoke, return {"messages": [response]}
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node); builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")
    return builder.compile()

def build_agent_graph(*, generation_model, base_url, num_ctx, tools) -> CompiledStateGraph:
    llm_with_tools = _build_tool_chat_model(generation_model=generation_model,
                                            base_url=base_url, num_ctx=num_ctx).bind_tools(tools)
    return compile_agent_graph(llm_with_tools, tools)
```

`route_after_agent(state)` returns `"tools"` if the last message carries
`tool_calls`, else `END` — a module-level function, itself unit-tested.

**Deterministic `needs_tradition` short-circuit (spec FR7).** Found in live
testing: when `get_symbol` returns `needs_tradition` (no interpretive content
at all — just a tradition list), a local model sometimes doesn't stop to ask;
it composes a plausible-sounding answer anyway, inventing denotations/meanings
that exist nowhere in any tool result. Sampling-dependent (not reproduced on
every attempt with either `qwen2.5:3b` or `llama3.2`), so it cannot be
prompted away with confidence — the fix removes the generation model from this
one decision entirely rather than asking it more forcefully to behave.

Added a third node, `clarify_tradition_node`, and a conditional edge after
`tools` (previously an unconditional `tools → agent`):

```python
def route_after_tools(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if isinstance(last_message, ToolMessage) and last_message.name == "get_symbol":
        payload = _safe_json_loads(last_message.content)
        if isinstance(payload, dict) and payload.get("needs_tradition"):
            return "clarify_tradition"
    return "agent"

def clarify_tradition_node(state: AgentState) -> dict:
    payload = _safe_json_loads(state["messages"][-1].content)
    traditions = ", ".join(payload.get("traditions", ()))
    symbol = payload.get("symbol", "this symbol")
    text = f"Which tradition would you like to use for {symbol}? Available: {traditions}."
    return {"messages": [AIMessage(content=text)]}
```

Wiring: `builder.add_node("clarify_tradition", clarify_tradition_node)`,
`builder.add_conditional_edges("tools", route_after_tools, {"agent": "agent",
"clarify_tradition": "clarify_tradition"})`, `builder.add_edge("clarify_tradition",
END)`. Every other tool's result still routes `tools → agent` as before — this
only intercepts the one narrow, fully-enumerable case where the tool result
*is* the complete set of facts to convey (a tradition list) and composing a
reply is pure formatting, not synthesis, so removing the model costs nothing
in capability.

`tools.py::get_symbol`'s `needs_tradition` payload gains a `"symbol"` key (the
sign's canonical name) so the deterministic message can name it — previously
absent since the LLM was expected to already have the name from its own
request.

This does not generalize to other tool errors/edge cases (e.g. a `MythrixError`
`{"error": ...}` payload) — those still route through the model, which must
compose a response acknowledging the failure. Scoped narrowly to the one
demonstrated, most-severe case: stating specific symbolic content grounded in
nothing at all.

The turn bound (spec FR12) turned out to be a **runtime**, not compile-time,
concern: LangGraph's `recursion_limit` is a `config` value passed at
`graph.stream(...)`/`.invoke(...)` time, not a graph-construction parameter, so
`build_agent_graph`/`compile_agent_graph` take no `max_tool_iterations` — one
compiled graph is reused across every turn, and `runner.run_turn` supplies the
bound per call.

**Chat client note (resolved).** `bind_tools` is a `ChatOllama`/LangChain-model
method, but `OllamaChatClient` (`core/synthesis/chain.py`) wraps `ChatOllama`
behind a narrow `invoke(prompt) -> str` with no tool-binding surface. `graph.py`
builds its **own** tool-capable `ChatOllama` (`_build_tool_chat_model`,
constructed from `Settings.generation_model`/`ollama_base_url`) rather than
reusing `OllamaChatClient`. The small "model not found"/"daemon unreachable"
message-text mapping is **duplicated** into `_build_tool_chat_model`, not
factored out of `core/synthesis/chain.py` into a shared helper as first
sketched — factoring it would be one more edit to `core/` purely for the
agent's benefit, and this package is otherwise self-contained from `core/`
beyond the read-only `list_semiotic_systems` addition. `OllamaChatClient`
itself is unchanged, still used narrowly by the `summarize_passage` tool.

### `runner.py` — UI-free turn driver

```python
@dataclass
class TurnResult:
    reply: str
    tool_calls: list[str]      # ordered tool-name trace (spec FR10)

def run_turn(graph, history: list, user_text: str, *, max_tool_iterations: int) -> tuple[list, TurnResult]:
    ...  # append HumanMessage, stream graph, collect tool-call names, return (new_history, TurnResult)
```

Streaming the graph (`stream_mode="values"`) lets the runner collect the tool
trace and lets the CLI print breadcrumbs live. Keeping this terminal-free is what
makes the loop testable without stdin and reusable by the future `/api/agent`
endpoint.

### `cli.py` — the agent's own entrypoint (no `mythrix` CLI changes)

The agent ships its **own** Typer app and console script, so it touches neither
`core/cli/` nor `cli/main.py`. Same testable-core / thin-wrapper split as
`query.py`, but the app lives inside the agent package:

```python
# src/mythrix/agent/cli.py
import typer
app = typer.Typer(name="mythrix-agent", help="Conversational operator for Mythrix.")

def run_agent(*, graph, max_tool_iterations, read_line, write) -> int:
    """Testable REPL core: injected graph + I/O callables; loops, prints the
    tool trace then the reply; returns an exit code."""
    ...

@app.command()
def main() -> None:
    settings = Settings()
    stores = build_stores(settings)                         # core public API
    model = settings.agent_model or settings.generation_model
    chat_client = OllamaChatClient(generation_model=model, base_url=settings.ollama_base_url,
                                   num_ctx=settings.generation_num_ctx)   # fail-fast, spec FR8
    tools = build_tools(stores, settings, chat_client)
    graph = build_agent_graph(chat_client, tools, max_tool_iterations=settings.agent_max_tool_iterations)
    raise typer.Exit(run_agent(graph=graph, max_tool_iterations=settings.agent_max_tool_iterations,
                               read_line=input, write=typer.echo))
```

- REPL over stdlib `input()` (no `prompt_toolkit`): read a line, `run_turn`, print
  the tool trace (`🔧 query_symbol …`) then the reply; `exit`/`quit`/EOF ends.
  History persists in-process only (spec: non-goal on cross-restart persistence).
- Exposed as a separate console script in `pyproject.toml` (see Dependency):
  `mythrix-agent = "mythrix.agent.cli:app"`. The existing `mythrix` CLI
  (`cli/main.py`) is **not modified** — `query`/`load-symbols`/`load-documents`
  stay exactly as they are (spec FR13).

## Config: `core/config.py::Settings`

Reuse `generation_model` (live `.env` = `qwen2.5:3b`), `ollama_base_url`,
`generation_num_ctx`. Add two fields only:

- `agent_model: str | None = None` — optional override; falls back to
  `generation_model`.
- `agent_max_tool_iterations: int = 8` — the per-turn tool-call bound (spec FR12).

## Dependency & entrypoint

Add **`langgraph`** to `pyproject.toml` `[project.dependencies]` (currently
absent). `langchain-core` (for `@tool`, message types) comes transitively with
the existing `langchain`/`langchain-ollama`; pin it explicitly only if the tool
imports need it. No `prompt_toolkit` (prueba2 used it; the REPL uses stdlib
`input()`).

Add the agent's console script to `[project.scripts]` (alongside the existing
`mythrix = "mythrix.cli.main:app"`):

```toml
[project.scripts]
mythrix = "mythrix.cli.main:app"
mythrix-agent = "mythrix.agent.cli:app"
```

This is the only `pyproject.toml` change beyond the dependency, and it is
additive — the `mythrix` entrypoint is untouched.

## Remove

Delete `src/mythrix/prueba2.py` — its pattern now lives, tested and injected, in
`agent/`.

## Testing

Follows the existing `tests/unit` pattern (inject fakes; no Ollama/Kùzu/Chroma):

- **`KuzuGraphStore.list_semiotic_systems`:** returns the distinct, ordered
  systems for signs that have a manifestation; excludes a system whose signs have
  none (mirrors `list_signs`).
- **`tools.py`:** each wrapper against a fake `Stores` / fake `ChatClient`
  returns the expected compact shape; `query_symbol`/`fetch_segments`/`get_symbol`
  map the real result models to dicts with citations/locators; `list_symbols`/
  `list_traditions` scope correctly by `semiotic_system`; `get_symbol` resolves a
  single-tradition sign automatically and returns `needs_tradition` for a
  multi-tradition sign with none given, and `error` for an unknown slug; a
  `MythrixError` from a fake store is returned as a structured error string, not
  raised. **Read-only invariant:** assert the built tool-name set is exactly the
  seven read-only tools.
- **`graph.py`:** drive `build_agent_graph` with a stub tool-capable chat client
  that emits a scripted `tool_calls` message on the first pass and a plain answer
  on the second; assert `ToolNode` runs `query_symbol` and the loop terminates at
  `END`; assert `route_after_agent` routes tool-call vs plain messages correctly;
  assert the recursion bound ends a runaway loop.
- **`runner.py`:** `run_turn` appends history, returns the ordered tool-name
  trace, and preserves history across two turns.
- **CLI `run_agent`:** with a fake graph and injected `read_line`/`write`
  callables, one scripted turn prints the trace and reply and returns exit code 0;
  an unresolvable model yields a clean error and non-zero exit. Assert
  `mythrix --help` is unchanged (agent is a separate `mythrix-agent` script).
- **Integration (opt-in `@pytest.mark.requires_ollama`):** one real turn against
  the live `.mythrix/` store — mirrors the existing `OllamaChatClient` integration
  marker.

## Verification (end-to-end, manual)

Needs Ollama running with the embedding + generation models and the live
`.mythrix/` store:

1. `uv run mythrix-agent`.
2. "list the symbols" → agent calls `list_semiotic_systems` and asks whether to
   use `tarot` or `hebrew_alef_bet` (spec FR5) rather than listing across both.
3. "tarot" → agent calls `list_symbols(semiotic_system="tarot")`; the system is
   reused for the rest of the session.
4. "tell me about The Magician" → agent calls `get_symbol("the-magician")`;
   since it has two traditions (`rider-waite`, `marseille`) with none given, the
   agent presents them and asks which; "rider-waite" → `get_symbol` returns its
   interpretants, denotation, correspondences, and citations.
5. "what converges on Qoph in tarot?" → agent calls `query_symbol`, returns
   ranked hotspots with citations (e.g. Genesis 21:6–7).
6. "show me the surrounding passage" → agent calls `fetch_segments` on that
   source/ordinal range.
7. "summarize that passage for the child/laughter interpretants" → agent calls
   `summarize_passage`.
8. Confirm the tool trace prints for each turn and history carries across turns.
6. `ruff check .` and `ruff format .` clean; `uv run pytest` green.
7. Confirm `mythrix query` / `/api/query` output is byte-for-byte unchanged
   (agent is additive).

## ADR

Warranted → **ADR 0006** (`0006-conversational-agent-orchestration-boundary.md`).
The decision — a generation model may *orchestrate* Mythrix (converse, select
tools) but the retrieval it drives stays deterministic, embedding-only, and
cited, and the agent is local-Ollama-only and read-only — is a lasting boundary
of architectural weight (it governs where generated text is allowed, per master
FR11/FR12/FR29), not a local, reversible implementation detail. Write it before
implementation.

## Risks / trade-offs

- **Small-model tool-calling reliability.** `qwen2.5:3b` may occasionally
  mis-format a tool call or drop list items. Mitigations: a firm system prompt
  (spec FR5/FR6), structured tool returns, and the `agent_model` override to run
  a stronger local model. Not a correctness risk to the *engine* — retrieval is
  unchanged and cited; the risk is confined to the agent's phrasing/selection.
- **Duplicated `ChatOllama` construction** (option 1 above). Mitigated by
  factoring the error-mapping helper out of `OllamaChatClient` so both call sites
  share the empirically-derived matching.
- **No streaming token output in the CLI.** The REPL prints the reply once the
  turn completes. Acceptable for v1; a future `/api/agent` can stream.
- **In-process history only.** By design (non-goal); a long session grows the
  context sent to a small local model — bounded in practice by `num_ctx` and the
  single-user tool's short sessions.
