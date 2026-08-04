# ADR-023 — In-graph citation retry replaces the one-shot post-hoc reject

- **Status**: Accepted
- **Date**: 2026-08-03
- **Extends**: [ADR-006](adr-006-conversational-agent-orchestration-boundary.md), [ADR-022](adr-022-tool-owned-opaque-grounding-ids.md)
- **Realized by**: [agent.md](../interfaces/agent.md) FR-AG-06

## Context

Citation validation (`agent/citations.py::find_invalid_markers`, ADR-022) has always run as a single post-hoc gate in `turn_service.py::stream_chat_turn`, after the model's tool-calling loop has already ended: the final reply's `[G...]`/`[S...]` markers are checked against this turn's tool results, and any invalid marker discards the *entire* reply in favor of one generic apology (`_CITATION_FAILURE_MESSAGE`). The model never sees that check fail and never gets a chance to correct it — a wrong marker and a wrong answer are handled identically.

Real-model integration testing this session (`tests/integration/test_agent_grounding_ids.py`, run against `qwen3:1.7b`) showed this reject-only handling is a poor fit for the actual failure mode: across many turns, the model never once fabricated a grounding id — the opaque, independently-generated ids ADR-022 introduced held up completely — but it frequently *formatted* a real one wrong (prose instead of brackets, or an invented citation notation of its own). This is a recoverable mistake, not a grounding failure, and a model shown exactly which marker was wrong is far better positioned to fix it than one asked to redo an entire answer with no feedback.

An earlier, uncommitted proof of concept (removed as dead code earlier this session) already carried a `# FIXME MOVE TO A VALIDATION NODE WITH RETRY AND PUSHBACK` comment at the exact point this reject happens — this decision resolves that.

## Decision

Citation validation for the model-driven conversational turn (the `agent`/`tools` loop `compile_agent_graph` builds) moves from `turn_service.py`'s post-hoc check into a new deterministic graph node, `validate_citations_node` (`agent/graph/nodes/citation_check.py`), reached whenever `agent_node` produces a reply with no further tool calls:

- Valid reply (or a turn where only listing tools — `list_signs`/`list_traditions`/`list_semiotic_systems` — were called, which carry no citations to validate): no-op, the graph proceeds to `END` exactly as before.
- Invalid reply, retries remaining (bounded by `Settings.citation_max_retries`, default `2`): a corrective `HumanMessage` (`agent/prompts.py::render_citation_pushback`) naming the specific invalid marker(s) is appended, and the graph routes back to `agent` for another generation attempt.
- Invalid reply, retries exhausted: the same `CITATION_FAILURE_MESSAGE` the old post-hoc check used (moved to `agent/citations.py`, now public) is substituted as the final reply, and the graph proceeds to `END`.

A new turn-scoped state field, `turn_start_index` (`agent/graph/state.py`), fixes where in `state["messages"]` this turn began — set once by `runner.py::stream_turn` (`len(history)`, the index of the newly-appended `HumanMessage`) and never touched again mid-turn. This is what lets `validate_citations_node` find "this turn's tool messages" reliably across zero or more retry loops, since a naive "scan back to the most recent `HumanMessage`" would find its own pushback instead of the turn's real boundary once a retry has happened.

The tool-payload-reading logic that finds a `get_sign`/`query_sign`/`fetch_segments` tool result's `grounding_id`s is extracted from `turn_service.py::_build_valid_marker_ids` into a new, lower-level shared module, `agent/citation_grounding.py`, imported by both `turn_service.py` (unchanged for its own remaining callers) and the new node — `agent/citations.py` stays deliberately typeless (its own docstring: "works on text and a set of valid identifiers... never on retrieval or graph models"), and `turn_service.py` is a higher-level orchestrator that composes the graph rather than something the graph should depend on, so the shared logic could not live in either of those without inverting one direction or the other.

`turn_service.py`'s own post-hoc check is **not removed**. It remains the sole citation gate for `/augment`'s reply (`run_augment_node`'s consolidation, including its `[R#]` region markers — a distinct, position-based id space, FR-AU-30, out of scope here) and continues to run, now redundantly, as a final backstop on the conversational path too — a reply that reaches it from the new node is expected to already be valid or already be the fallback message, so in practice it should never trip there, but removing it would require a stronger guarantee about the node's coverage of every path through the graph than this change establishes.

## Consequences

- A model that gets a citation format wrong gets a bounded number of chances to fix it, with concrete feedback naming what was wrong, before the turn falls back to the generic apology — strictly better than today's immediate, uninformative reject for the large class of failures that are formatting mistakes rather than fabrication.
- `Settings.citation_max_retries` is a new small, tunable budget, independent of `agent_max_tool_iterations` — a turn's total step count can now be tool-call iterations *and* citation retries combined, still bounded by the same outer `recursion_limit` `runner.py` already applies, so a pathological turn cannot loop unboundedly even if both budgets are set generously.
- `validate_citations_node` only sits on the `agent`-driven path (`route_after_agent`'s no-tool-calls branch). `/augment` (`plan_augment`/`run_augment`, ADR-012/ADR-015) is unaffected by design — its citation risk profile and generation shape (a single hierarchical consolidation call, not a conversational loop) differ enough that folding it into the same retry mechanism is a separate decision, not assumed here.
- A pushback is delivered as a `HumanMessage` appended to `state["messages"]`, the first time this codebase has injected a message into persisted turn history that did not originate from the real user or a tool. It is scoped to the graph's internal retry loop only — `turn_service.py`'s history-persistence logic is unchanged, and a pushback/retry cycle that ends in a valid reply leaves no trace of the attempt in what `session.history` carries forward, exactly as a discarded intermediate reply already didn't under the old scheme.

## Alternatives considered

- **Leave the one-shot post-hoc reject as-is.** Rejected — this decision's entire motivation: real-model testing showed most invalid-marker cases are recoverable formatting mistakes, and discarding a correct-but-mis-cited answer wholesale is a worse outcome for the user than giving the model one clear chance to fix it.
- **Validate and retry inside `agent_node` itself, rather than a separate node.** Rejected — mixes model-invocation concerns with citation-integrity concerns in one function, and the codebase's existing precedent for a deterministic post-generation check is its own node (`clarify_node`, intercepting a tool result before it reaches the model) rather than inline logic in the node that calls the model.
- **Extend the retry mechanism to `/augment`'s consolidation reply too.** Rejected for this pass — `run_augment_node` is a deterministic multi-step pipeline (read region → augment → consolidate), not the conversational tool-calling loop; giving it a comparable self-correction path is a materially different, separately-scoped change.
