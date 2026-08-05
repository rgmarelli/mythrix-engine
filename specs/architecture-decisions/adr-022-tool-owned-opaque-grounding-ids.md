# ADR-022 — Tool-owned, opaque grounding ids replace positional citation numbering

- **Status**: Accepted
- **Date**: 2026-08-03
- **Extends**: [ADR-006](adr-006-conversational-agent-orchestration-boundary.md)
- **Realized by**: [agent.md](../interfaces/agent.md) FR-AG-06; [retrieval.md](../retrieval/retrieval.md) FR-RT-04

## Context

`[G#]`/`[S#]` grounding markers (`agent/citations.py`) exist to let `turn_service.py` validate, in code, that every marker in a model-authored reply names an item a tool actually returned this turn. Until now, both sides of that contract used the same convention independently: the system prompt told the model to number tool items itself, in the order they appear, starting at 1; `turn_service.py` then re-derived the "correct" ids by counting the same items positionally across the turn's tool results.

Because the valid-id set is a small range of sequential integers reconstructed from a count the model never sees directly, a model doesn't need to have actually grounded a claim in a specific tool-returned item to produce a marker that passes validation — it only has to guess a plausible small integer that happens to fall within however many items that turn's tools returned. The convention that exists to prove grounding can be satisfied without it.

An earlier prototype moved id *assignment* into the tool by threading a running counter through agent state, which is the right direction, but still derived each id from a predictable positional formula — it didn't close the guessing gap, and generalizing it to every citable tool would mean converting each into stateful, counter-threading machinery for no corresponding benefit once the counter no longer needs to encode anything.

## Decision

The tool that returns a citable item is the sole author of that item's grounding id, and the id is an **opaque, independently-generated token per item** — never derived from position, a shared counter, or any other reconstructable sequence:

- Every tool result item that can be cited (a `get_sign` citation, a `query_sign`/`fetch_segments` segment) carries its own `grounding_id`, assigned at render time from a random, `uuid4`-derived suffix. No shared state crosses tool calls or turns to produce it — each item's id is generated independently, with no ordering dependency on any other item.
- `turn_service.py` reads each item's `grounding_id` directly off the tool's own payload instead of reconstructing a count; it no longer needs to know how many citable items a tool returned, only where to find the id it already assigned.
- The marker regex widens to accept the new hex-suffixed ids; validation and stripping logic are unchanged, since they already operate on "a marker shape" against a caller-supplied `valid_ids` set, not on any numbering policy.
- The system prompt no longer asks the model to number items itself; it states that each tool result item carries its own grounding id, to be copied verbatim, never invented or renumbered.
- `[R#]` region markers (augmentation's consolidation output) are explicitly unaffected. They stay sequential and position-based by deliberate, separate design — a skipped region must leave a visible numbering gap — and carry a different, already-low guessing risk: the model is handed the exact label vocabulary directly in the consolidation prompt rather than asked to reconstruct a count from tool results it must count itself.

## Consequences

- A model cannot produce a marker that passes validation without having actually seen that exact opaque id echoed in a tool result this turn — guessing a small integer no longer works, since there is no small, predictable range to guess within.
- `get_sign`, `query_sign`, and `fetch_segments` stay plain, directly-unit-testable tool functions returning plain dicts/lists. No tool needs state-threading machinery to participate in grounding-id assignment, and the prototype's counter field is removed rather than generalized.
- `turn_service.py`'s contract with each tool shrinks to "find the `grounding_id` field on each citable item," rather than "know precisely how each tool's citable items are shaped well enough to count them in the right order" — a smaller, more stable surface for a future citable tool to satisfy.
- Any future tool that returns citable items must mint its own grounding id at render time; a tool that omits it produces items that can never be validated against, so the omission fails closed (no citation ever validates) rather than silently reintroducing positional guessing.
- Ids are per-call and not stable across repeated tool calls within or across turns: the same underlying segment fetched twice gets two different ids. This is an accepted trade — the existing sequential scheme had the same property, and grounding ids exist to validate a marker against *this turn's* tool results, not to serve as a durable cross-turn identifier for a passage (`region_id` already serves that purpose where one is needed).

## Alternatives considered

- **Generalize the prototype's shared-counter approach to every citable tool.** Rejected — the counter itself doesn't need to be shared once the id is independently random rather than counter-derived; keeping it would add state-threading to more tools and break their existing direct-invocation unit tests, for no benefit over independent per-item randomness.
- **Content-derived deterministic ids (e.g. a hash of source and ordinal).** Rejected for this pass — it would make the same segment's id stable across calls, which nothing in the system currently needs, at the cost of extra implementation complexity for no guessing-resistance benefit over independent randomness; deterministic ids remain an option for a future need that specifically requires cross-call stability.
- **Bring `[R#]` region markers into the same opaque-id scheme "for consistency."** Rejected — `[R#]`'s guessing risk is already low for a structurally different reason (the model is given the valid label set directly in-prompt, not asked to reconstruct one), and its gap-preserving behavior depends on sequential, position-based numbering; changing it is a separate decision with no bearing on the guessing gap this ADR closes.
