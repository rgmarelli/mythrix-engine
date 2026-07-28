# Agnostic Interpretant Query — Tasks

Derived from [plan.md](plan.md), realizing [specs/interfaces/agnostic-query.md](../../interfaces/agnostic-query.md). Check off as each lands; keep this file until the feature is confirmed complete (per `CLAUDE.md`).

The ad-hoc retrieval core (`AdhocTerm`, `AdhocQueryValidationError`, `execute_adhoc_query`, `POST /api/query/adhoc`) and its tests are already implemented and stay unchanged — no task below touches them.

## Removals (plan §2)

- [x] Remove `execute_adhoc_query_tool` from `agent/tools.py`, drop it from `build_tools`'s returned list, and restore the module docstring's tool count to seven.
- [x] Remove the `execute_adhoc_query_tool` rule from `agent/prompts.py::SYSTEM_PROMPT`.
- [x] Remove `_rewrite_query_command`, `_QUERY_PREFIX`, `_build_instructions`, and the `build_instructions` import from `agent/turn_service.py`.
- [x] Delete `agent/instructions.py` and `tests/unit/test_agent_instructions.py`.
- [x] Remove the four `execute_adhoc_query_tool` tests from `tests/unit/test_agent_tools.py`; restore the tool-set test to seven tools.

## Command parsing (plan §3)

- [x] Add `agent/adhoc_query.py` with `QUERY_COMMAND`/`CONFIRM_COMMAND`, `PendingAdhocQuery`, `command_of`, and `is_adhoc_command` — pure functions, no LangGraph imports.
- [x] Implement `parse_query_command(rest)`: comma split, `rpartition(":")` directive suffix, `AdhocQueryValidationError` on no terms / empty value / unknown directive.
- [x] Implement confirmation-reply rendering (parsed list plus the literal `/query-confirm <id>` command) and the `confirm_query` / `execute_query` instruction builders.

## Graph wiring (plan §4)

- [x] Add `pending_query` and `instructions` keys to `AgentState`.
- [x] Add `route_input`, replacing `builder.add_edge(START, "agent")` with a conditional edge on `START`; edge `parse_query` and `execute_query` to `END`.
- [x] Implement `parse_query_node`: mints a `uuid4().hex[:8]` id, returns the confirmation `AIMessage`, the new pending query, and one `confirm_query` instruction; on a parse error returns the error reply with `pending_query=None` and no instructions.
- [x] Implement `execute_query_node`: matching id → one `execute_query` instruction from the stored terms and `pending_query=None`; unknown/missing/consumed id → error reply, no instructions, existing pending preserved.

## Turn driver (plan §5)

- [x] Add a `pending_query` parameter to `run_turn` and pass it (plus `instructions: []`) into the graph input dict.
- [x] Add `instructions` and `pending_query` to `TurnResult`, read off the final state; default them on the `GraphRecursionError` path.

## Session state and turn plumbing (plan §6)

- [x] Add `pending_query: PendingAdhocQuery | None = None` to `agent/sessions.py::SessionState`.
- [x] Clear `session.pending_query` alongside `session.history` on thread reset in `run_chat_turn`.
- [x] Pass `session.pending_query` into `run_turn`; assign `session.pending_query = result.pending_query` afterwards.
- [x] Gate post-processing on `is_adhoc_command(message)`: skip the `session.history` assignment and skip citation validation on a command turn.
- [x] Build `AgentTurnResponse.instructions` from `result.instructions`; widen `AgentInstruction.type` to `Literal["confirm_query", "execute_query"]`.

## Frontend contract (plan §7)

- [x] Widen `AgentInstructionWire.type` in `web/src/api/types.ts` to `'confirm_query' | 'execute_query'`.

## Tests (plan §8)

- [x] Add `tests/unit/test_agent_adhoc_query.py` covering the parser (plain/`:exact`/`:filter`/mixed, whitespace, empty command, empty value, unknown directive) and `command_of` distinguishing `/query` from `/query-confirm`.
- [x] Add `route_input` branch tests and node-level tests (valid parse, parse error, matching id, wrong id, no pending) to `tests/unit/test_agent_graph.py`.
- [x] Add `run_chat_turn` tests with a graph stub that raises if the model path is reached: `/query` emits one `confirm_query`, leaves `session.history` unchanged, never invokes the model.
- [x] Add `run_chat_turn` tests for confirmation: one `execute_query` with the stored terms; a repeat of the same command yields none.
- [x] Add `run_chat_turn` tests for the pending-query lifecycle: a second `/query` supersedes the first; a thread reset discards the pending query; a malformed `/query` creates none.
- [x] Add a regression test that `/query [S1]` survives citation validation intact.
- [x] Add a test that an ordinary turn following `/query` reaches the graph with history identical to the no-command case (FR-AQ-16).

## Close-out

- [x] `ruff check .` / `ruff format .` clean; `npx tsc -b`, `npx vitest run`, `npx oxlint` clean in `web/`.
- [x] Full `uv run pytest` green; confirm no behavior change to any existing tool, the CLI `query` command, or non-agent API routes.
- [x] Verify the agent's registered tool set is back to exactly FR-AG-03's seven tools and the system prompt gained nothing (FR-AQ-17).
- [ ] Get user confirmation the feature (this increment's scope) is complete, then remove `plan.md`/`tasks.md` per `CLAUDE.md`'s SDD rules.
