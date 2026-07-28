# Agnostic Interpretant Query — Implementation Plan

Realizes [specs/interfaces/agnostic-query.md](../../interfaces/agnostic-query.md) (FR-AQ-01–21), scoped by [ADR-010](../../architecture-decisions/adr-010-agnostic-adhoc-interpretant-query.md). Backend/agent-side only — `web/` changes are limited to keeping the wire contract in sync; nothing consumes instructions yet.

Part of this feature is already implemented and stays as-is (§1). The rest replaces an earlier model-driven design (a `/query` hint rewrite priming the model to parse terms, plus an `execute_adhoc_query_tool` gated by a system-prompt rule) with deterministic command handling, per the amended ADR-010.

## 0. Where the command handling lives

Both commands are handled as **nodes in the agent's LangGraph state machine** (`agent/graph.py`), reached by a deterministic router on the `START` edge, each running to `END` without touching the `agent` node.

The precedent is `clarify_node` (`graph.py:102`, wired at `:153`/`:157`): a node that builds its reply directly from structured data, calls no model, and edges straight to `END` — justified in its own docstring as keeping a pure-formatting reply out of the model's hands (ADR-006). `parse_query` and `execute_query` are that same shape. Handling them outside the graph instead would leave `graph.py` describing progressively less of what a turn actually does.

`/summarize` stays a pre-graph message rewrite for now (`turn_service.py:48`). It is a separate concern — it *wants* the model, and its rewrite has its own defect worth fixing (it replaces the user's `HumanMessage`, so `session.history` permanently holds a fabricated user turn). Out of scope here; tracked as a follow-up.

## 1. Ad-hoc retrieval core (FR-AQ-18–21) — already implemented, unchanged

`AdhocTerm` (`core/models.py`), `AdhocQueryValidationError` (`core/errors.py`, mapped to 422 in `api/errors.py`), `execute_adhoc_query` (`core/query_service.py`) building the sentinel `Tradition`/`Sign`/`Manifestation` and feeding it to an unmodified `RetrievalPipeline`, and `POST /api/query/adhoc` (`api/routes.py`) all stay exactly as they are, along with their tests. No task below touches them.

## 2. Removals

The earlier increment's model-driven half comes out:

- `agent/tools.py` — `execute_adhoc_query_tool`, its entry in `build_tools`'s returned list, and the module docstring's "eight read-only tools" (back to seven). Restores FR-AG-03's tool set.
- `agent/prompts.py` — the `execute_adhoc_query_tool` rule. Nothing replaces it (FR-AQ-17).
- `agent/turn_service.py` — `_rewrite_query_command`, `_QUERY_PREFIX`, `_build_instructions`, and the `build_instructions` import.
- `agent/instructions.py` and `tests/unit/test_agent_instructions.py` — deleted. Instructions no longer originate from tool results, so the dispatch-by-tool-name module has no remaining purpose.
- `tests/unit/test_agent_tools.py` — the four `execute_adhoc_query_tool` tests; the tool-set test returns to seven.

## 3. Command parsing (FR-AQ-02–03, FR-AQ-06–07, FR-AQ-13–14)

**New module** `agent/adhoc_query.py`, holding everything deterministic about this path — pure functions and dataclasses, no LangGraph imports, so it is testable on its own and `graph.py` stays a wiring module.

```python
QUERY_COMMAND = "/query"
CONFIRM_COMMAND = "/query-confirm"


@dataclass(frozen=True)
class PendingAdhocQuery:
    id: str
    terms: tuple[AdhocTerm, ...]
```

**Command detection** (`command_of(message) -> str | None`) matches the *whole* head token, `message.strip().partition(" ")[0].lower()`, exactly as `_rewrite_summarize_command` (`turn_service.py:53`) does — a `startswith` check would make `/query-confirm` match `/query`.

**Parsing** (`parse_query_command(rest) -> tuple[AdhocTerm, ...]`, raising `AdhocQueryValidationError`):

- Split `rest` on `,`; strip each item; drop empty items. No item left → error.
- Per item, `value, sep, suffix = item.rpartition(":")`:
  - no `sep` → concept term, `AdhocTerm(value=item)`.
  - `sep` and `suffix` in `{"exact", "filter"}` → `AdhocTerm(value=value.strip(), directive=suffix)`; empty `value` → error.
  - `sep` and any other `suffix` → error naming the unknown directive. A term containing a literal `:` is therefore rejected rather than mis-parsed; the error text states the accepted syntax (FR-AQ-03).

**Ids** are `uuid4().hex[:8]` — short enough to retype by hand, which FR-AQ-06 depends on.

**Rendering** the confirmation reply (FR-AQ-06):

```
Parsed query:
- laughter
- child
- hundred [exact]
- pisces [filter]

Send `/query-confirm 7f3a1c9e` to run it.
```

**Instruction payloads** (FR-AQ-07, FR-AQ-13, FR-AQ-14 — no method, no path):

```python
{"type": "confirm_query", "payload": {
    "query_id": "7f3a1c9e",
    "terms": [{"value": "laughter", "directive": None}, ...],
    "confirm_command": "/query-confirm 7f3a1c9e",
}}

{"type": "execute_query", "payload": {"terms": [...]}}
```

`confirm_query` carries `confirm_command` verbatim so a consumer's affordance sends the identical string a human would type — one code path, not two (ADR-010).

## 4. Graph wiring (FR-AQ-01, FR-AQ-04–05, FR-AQ-08–12)

`AgentState` gains two keys alongside the existing `messages`/`context_summary`, both plain last-write-wins values (no reducer):

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    context_summary: str
    pending_query: PendingAdhocQuery | None
    instructions: list[dict]
```

**Router**, on the `START` edge — the one place command dispatch happens:

```python
def route_input(state: AgentState) -> str:
    command = command_of(state["messages"][-1].content)
    if command == CONFIRM_COMMAND:
        return "execute_query"
    if command == QUERY_COMMAND:
        return "parse_query"
    return "agent"


builder.add_conditional_edges(
    START, route_input, {"parse_query": "parse_query", "execute_query": "execute_query", "agent": "agent"}
)
builder.add_edge("parse_query", END)
builder.add_edge("execute_query", END)
```

`builder.add_edge(START, "agent")` (`graph.py:154`) is replaced by this. A router on `START` needs no node of its own; `route_after_agent`/`route_after_tools` and the whole `agent` ↔ `tools` ↔ `clarify` subgraph are untouched.

**`parse_query_node`** — parses; on `AdhocQueryValidationError`, replies with the error text, no instructions, and `pending_query=None` (FR-AQ-03: no pending query is created, and any prior one is dropped, keeping "at most one" unambiguous). On success, mints an id and returns:

```python
{
    "messages": [AIMessage(content=render_confirmation(terms, query_id))],
    "pending_query": PendingAdhocQuery(id=query_id, terms=terms),
    "instructions": [confirm_query_instruction(query_id, terms)],
}
```

**`execute_query_node`** — reads `state["pending_query"]`; the id in the message must equal `pending.id` (FR-AQ-09). Match → emits one `execute_query` instruction built from `pending.terms` (FR-AQ-10), replies that execution was requested, and returns `pending_query=None` (FR-AQ-12). No match, no pending, or missing id → reply saying so, no instructions, and returns `state["pending_query"]` unchanged so a mistyped id does not destroy it.

Both nodes call no model, mirroring `clarify_node`, so FR-AQ-01 holds structurally.

## 5. Turn driver (`agent/runner.py`)

`run_turn` gains a `pending_query` parameter (defaulting to `None`, like `context_summary` does) and passes it, plus `instructions: []`, in the graph input dict. `TurnResult` gains two fields read off the final state:

```python
@dataclass
class TurnResult:
    reply: str
    tool_calls: list[str]
    instructions: list[dict]
    pending_query: PendingAdhocQuery | None
```

On the `GraphRecursionError` path, both default to `[]`/`None` alongside the existing unchanged-`history` return.

## 6. Session state and turn plumbing (FR-AQ-05, FR-AQ-15–17)

`agent/sessions.py::SessionState` gains `pending_query: PendingAdhocQuery | None = None`, alongside `history`/`context`. It lives and dies with the session exactly as they do (FR-AG-20, and the spec's persistence non-goal) — no new lifecycle, no TTL.

In `agent/turn_service.py::run_chat_turn`:

- Thread reset (`:196–198`) clears `session.pending_query` alongside `session.history` (FR-AQ-05).
- `run_turn(...)` is called with `pending_query=session.pending_query`; afterwards `session.pending_query = result.pending_query`.
- A single predicate, `is_adhoc_command(message)` from `agent/adhoc_query.py`, gates the turn's post-processing. On a command turn:
  - `session.history` is **not** assigned, so FR-AQ-16 holds without any cleanup pass.
  - Citation validation is skipped. This matters concretely: the reply restates the user's own terms, so `/query [S1]` would otherwise trip `find_invalid_markers` and replace the whole turn with `_CITATION_FAILURE_MESSAGE`. Validation exists to police model-authored text (FR-AG-06); this text is backend-authored.
  - `backfill_from_tool_results`/`model_driven_reset` are no-ops anyway (no tool messages), but skipping them keeps the path explicit rather than incidentally correct.
- `instructions=[AgentInstruction(**i) for i in result.instructions]` on the response, matching how `_build_cards` builds `AgentCard(**card)` from dicts.
- `AgentInstruction.type` widens to `Literal["confirm_query", "execute_query"]`; `AgentTurnResponse.instructions` keeps its type and its `[]` default on every other path.

## 7. Frontend contract (no consumption)

`web/src/api/types.ts` — `AgentInstructionWire.type` widens to `'confirm_query' | 'execute_query'`. `client.ts` already passes `instructions` straight through; no other change, and nothing reads them yet.

## 8. Tests

**New**, `tests/unit/test_agent_adhoc_query.py` — the pure functions in isolation: plain/`:exact`/`:filter`/mixed lists, surrounding whitespace, empty command, empty term value, unknown directive, and `command_of` distinguishing `/query` from `/query-confirm`.

**`tests/unit/test_agent_graph.py`** (alongside the existing `clarify_node`/routing tests) — `route_input`'s three branches, and each node's returned state for: a valid parse, a parse error, a matching id, a wrong id, and no pending query.

**`tests/unit/test_agent_turn_service.py`** — through `run_chat_turn`, using a graph stub whose `agent` path **raises if invoked**, which is what actually proves FR-AQ-01/FR-AQ-16 rather than asserting on output shape:

- `/query <terms>` → reply names the parsed terms and the confirm command; exactly one `confirm_query` instruction; `session.history` unchanged; the model never invoked.
- Confirming turn → exactly one `execute_query` instruction carrying the stored terms; pending consumed (a repeat of the same command yields none).
- A second `/query` replaces the pending query; the superseded id no longer confirms.
- A thread reset (changed UI selection) discards the pending query.
- Malformed `/query` → error reply, no instructions, no pending created.
- `/query [S1]` → the reply survives intact (citation validation skipped), guarding the regression §6 names.
- An ordinary message after a `/query` turn reaches the graph with history identical to what it would have been without the commands (FR-AQ-16, asserted on the stub's received messages).

**Unchanged**: every `execute_adhoc_query` and `POST /api/query/adhoc` test in `test_query_service.py`/`test_api.py`.

## Risks / open items

- The `:` rule makes any term containing a colon a syntax error. Accepted for a fixed two-directive vocabulary; if real terms need colons, quoting is the follow-up, not a looser parse.
- Nothing consumes `confirm_query` yet, so the only way to confirm today is retyping the command from the reply text. That is by design (FR-AQ-06) and is what makes this increment testable, but it is a deliberately plain UX until the frontend increment lands.
- A user who replies "yes" gets an ordinary agent turn, and the model — which knows nothing about the pending query (FR-AQ-16) — will answer out of context. Acceptable per ADR-010's stated trade; if it proves confusing in practice, the fix is a frontend affordance, not model involvement.
- `/summarize` remains the one command handled outside the graph, now visibly inconsistent with `/query`. Its rewrite also replaces the user's own `HumanMessage` in stored history, which is a defect independent of this feature. Follow-up, not scope creep here.
