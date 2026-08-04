# ADR-022 — Tool-owned, opaque grounding ids replace positional citation numbering

- **Status**: Accepted
- **Date**: 2026-08-03
- **Extends**: [ADR-006](adr-006-conversational-agent-orchestration-boundary.md)
- **Realized by**: [agent.md](../interfaces/agent.md) FR-AG-06; [retrieval.md](../retrieval/retrieval.md) FR-RT-04

## Context

`[G#]`/`[S#]` grounding markers (`agent/citations.py`) exist to let `turn_service.py` validate, in code, that every marker in a model-authored reply names an item a tool actually returned this turn (FR-AG-06, FR-RT-04). Until now, both sides of that contract used the same convention independently: `agent/prompts.py`'s `SYSTEM_PROMPT` told the model to number tool items itself, in the order they appear, starting at 1; `turn_service.py::_build_valid_marker_ids` then re-derived the "correct" ids by counting the same items positionally across the turn's tool results (each `get_sign` citation is the next `G#`, each `query_sign`/`fetch_segments` segment is the next `S#`).

Because the valid-id set is a small range of sequential integers reconstructed from a count the model never sees directly, a model doesn't need to have actually grounded a claim in a specific tool-returned item to produce a marker that passes validation — it only has to guess a plausible small integer that happens to fall within however many items that turn's tools returned. The convention that exists to prove grounding can be satisfied without it.

An in-progress, uncommitted proof of concept started addressing this on `fetch_segments` alone: it threads a running `citation_count` through `AgentState` (a `LangGraph` `Annotated[int, operator.add]` field) via a `Command`-returning tool with `InjectedState`/`InjectedToolCallId`, and derives each segment's id from that counter (`f"S{6978 - seq_num}"`). This moved id *assignment* into the tool, which is the right direction, but the id itself is still a fully predictable, purely positional formula (counting downward from a fixed constant instead of upward from 1) — it does not close the guessing gap, and generalizing it to `get_sign`/`query_sign` would require converting two more plain, directly-unit-testable tools into `Command`-returning, state-threading ones for no corresponding benefit once the counter no longer needs to encode anything.

## Decision

The tool that returns a citable item is the sole author of that item's grounding id, and the id is an **opaque, independently-generated token per item** — never derived from position, a shared counter, or any other reconstructable sequence:

- `agent/tools/_shared.py` gains one helper, `_new_grounding_id(prefix: str) -> str`, returning `f"{prefix}{uuid4().hex[:6]}"` — the same `uuid4()`-based convention `commands/augment.py::new_augmentation_id` already uses for augmentation-run ids.
- Every tool result item that can be cited carries its own `grounding_id`, assigned at render time: each `get_sign` citation (`_render_graph_facts`), each `query_sign` segment (`_render_regions`), each `fetch_segments` segment. No shared state crosses tool calls or turns to produce it — each item's id is generated independently, with no ordering dependency on any other item.
- `turn_service.py::_build_valid_marker_ids` reads each item's `grounding_id` directly off the tool's own payload instead of reconstructing a count; it no longer needs to know how many citable items a tool returned, only where to find the id it already assigned.
- `agent/citations.py`'s marker regex widens from `<Letter>\d+` to accept the new hex-suffixed ids for `G`/`S`/`C`; validation and stripping logic (`find_invalid_markers`, `strip_markers`, `strip_all_markers`) are unchanged, since they already operate on "a marker shape" against a caller-supplied `valid_ids` set, not on any numbering policy.
- `agent/prompts.py`'s `SYSTEM_PROMPT` no longer asks the model to number items itself; it states that each tool result item carries its own grounding id, to be copied verbatim, never invented or renumbered.
- `[R#]` region markers (`commands/augment.py::region_label`, `specs/interfaces/augmentation.md` FR-AU-30) are explicitly unaffected. They stay sequential and position-based by deliberate, separate design — a skipped region must leave a visible numbering gap — and carry a different, already-low guessing risk: the model is handed the exact label vocabulary directly in the consolidation prompt rather than asked to reconstruct a count from tool results it must count itself.

## Consequences

- A model cannot produce a marker that passes validation without having actually seen that exact opaque id echoed in a tool result this turn — guessing a small integer no longer works, since there is no small, predictable range to guess within.
- `get_sign`, `query_sign`, and `fetch_segments` stay plain `@tool` functions returning plain dicts/lists. No tool needs `Command`, `InjectedState`, or `InjectedToolCallId` to participate in grounding-id assignment, and no `AgentState` field threads a citation count across tool calls — the discarded proof of concept's state-threading machinery (`AgentState.citation_count`) is removed rather than generalized.
- `turn_service.py`'s contract with each tool shrinks to "find the `grounding_id` field on each citable item," rather than "know precisely how each tool's citable items are shaped well enough to count them in the right order" — a smaller, more stable surface for a future citable tool to satisfy.
- Any future tool that returns citable items must mint its own `grounding_id` via `_shared.py::_new_grounding_id` at render time; a tool that omits it produces items `turn_service.py` can never validate a marker against, so the omission fails closed (no citation ever validates) rather than silently reintroducing positional guessing.
- Ids are per-call and not stable across repeated tool calls within or across turns: the same underlying segment fetched twice gets two different ids. This is an accepted trade — the existing sequential scheme had the same property (a re-fetched item was simply recounted), and grounding ids exist to validate a marker against *this turn's* tool results, not to serve as a durable cross-turn identifier for a passage (`region_id` already serves that purpose where one is needed).

## Alternatives considered

- **Generalize the proof-of-concept's shared-counter approach (`Command`/`InjectedState`/`AgentState.citation_count`) to `get_sign`/`query_sign` too.** Rejected — the counter itself doesn't need to be shared once the id is independently random rather than counter-derived; keeping it would add `Command`-wrapping and state-threading to two more tools, break their existing direct-`.invoke()` unit tests, and buy nothing over independent per-item randomness.
- **Content-derived deterministic ids (e.g. a hash of `source_id`+`ordinal`).** Rejected for this pass — it would make the same segment's id stable across calls, which nothing in the system currently needs, at the cost of extra implementation complexity (choosing and threading a stable hash input per tool) for no guessing-resistance benefit over independent randomness; deterministic ids remain an option for a future need that specifically requires cross-call stability.
- **Leave `[R#]` region markers unchanged in file but bring them into the same opaque-id scheme "for consistency."** Rejected — `[R#]`'s guessing risk is already low for a structurally different reason (the model is given the valid label set directly in-prompt, not asked to reconstruct one), and FR-AU-30 depends on the numbering being sequential and position-based for its gap-preserving behavior; changing it is a separate decision with no bearing on the `G`/`S` guessing gap this ADR closes.
