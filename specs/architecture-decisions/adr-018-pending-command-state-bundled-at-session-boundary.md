# ADR-018 — Pending command confirmations are bundled into one value object at the session boundary

- **Status**: Accepted
- **Date**: 2026-07-29
- **Realized by**: `agent/commands/__init__.py::PendingCommands`

## Context

[ADR-010](adr-010-agnostic-adhoc-interpretant-query.md) and
[ADR-015](adr-015-deterministic-augmentation-over-viewer-regions.md) each gave
their command a "parse now, confirm later" record — `PendingAdhocQuery` and
`PendingAugmentation` — held in session state under a backend-generated id
until a matching confirm command consumes it (agnostic-query.md FR-AQ-04–05;
augmentation.md FR-AU-05, FR-AU-08). Each addition threaded its own field
through every layer that carries state across a turn: `SessionState`
(`agent/sessions.py`), `TurnResult` (`agent/runner.py`), and `stream_turn`'s
parameter list, alongside the pair of independent keys each already held on
`AgentState` (`agent/graph/state.py`).

`stream_chat_turn` (`agent/turn_service.py`) is where this repetition was most
visible — thread-reset, the call into `stream_turn`, and the post-turn
write-back each had one hardcoded line per pending-capable command:

```python
session.pending_query = None
session.pending_augmentation = None
...
pending_query=session.pending_query,
pending_augmentation=session.pending_augmentation,
...
session.pending_query = result.pending_query
session.pending_augmentation = result.pending_augmentation
```

`stream_chat_turn`'s job is to carry a turn's session-scoped state across the
HTTP request boundary; it has no reason to know the name or count of
individual commands with pending state. But with one field per command, every
future command needing this pattern would mean editing `stream_chat_turn`
(and `SessionState`, `TurnResult`, `stream_turn`'s signature) again, in
lockstep, forever.

Inside the LangGraph graph itself, this repetition is not a problem: each
node returns only the state keys it changes, and LangGraph merges those
partial updates per key. That is exactly why `plan_augment_node` (augment.py)
never has to read or preserve `pending_query`, and `parse_query_node`
(adhoc.py) never has to touch `pending_augmentation` — the two commands'
pending state is, and must remain, genuinely independent: a pending `/query`
and a pending `/augment` can be outstanding simultaneously, each scoped to "at
most one pending of that type," not "at most one pending confirmation
overall."

## Decision

A single value object, `PendingCommands` (`agent/commands/__init__.py`), one
field per pending-capable command, is the one thing that crosses the session
⇄ graph boundary:

- `SessionState.pending` and `TurnResult.pending` are each one
  `PendingCommands` field, replacing the one-field-per-command layout.
- `stream_turn` (`agent/runner.py`) takes and returns one `pending` value.
  It is the *only* place that translates between the bundled representation
  and the graph's two independent state keys — unpacking
  `pending.query`/`pending.augmentation` into the initial graph state, and
  re-assembling a `PendingCommands` from `final_state`'s two keys on the way
  out.
- `AgentState` and every node under `graph/nodes/` are unchanged: they keep
  reading and writing `pending_query`/`pending_augmentation` as two
  independent keys, preserving LangGraph's per-key merge semantics that let
  one command's node ignore another command's pending field for free.

## Consequences

- `stream_chat_turn` no longer names individual commands: its thread-reset
  clear, its call into `stream_turn`, and its session write-back are each one
  line instead of one-per-command.
- A third pending-capable command adds one field to `PendingCommands` and two
  lines to `stream_turn`'s translation (unpack going in, pack coming out).
  `turn_service.py` and `sessions.py` need no changes at all.
- The graph and session layers now use two different shapes for the same
  data (two independent `AgentState` keys vs. one bundled `SessionState`/
  `TurnResult` field), with `stream_turn` carrying the translation cost. This
  is intentional, not an oversight: see Alternatives.
- `PendingCommands` is frozen, like `PendingAdhocQuery`/`PendingAugmentation`,
  so it can be treated as an immutable snapshot at every layer that holds it.

## Alternatives considered

- **Bundle inside `AgentState` too** (`pending: PendingCommands` as a single
  graph state key instead of two). Rejected — it would push the coupling this
  ADR removes down one layer: every node that sets one sub-field would first
  have to read and explicitly carry forward the other's current value (e.g.
  `plan_augment_node` reconstructing `state["pending"]` with `query`
  preserved), work LangGraph's per-key partial-update merge currently gives
  every node for free. The bundling this ADR chooses stops at the boundary
  where the translation is a fixed, one-time cost (`stream_turn`) rather than
  a per-node, per-command one.
- **Merge the two pending records into one nullable slot** (at most one
  pending confirmation of any kind at a time). Rejected outright — it is a
  behavior change, not a representational one: a pending `/query` and a
  pending `/augment` are independently scoped today (FR-AQ-05, FR-AU-08), and
  confirming one must not silently drop the other.
