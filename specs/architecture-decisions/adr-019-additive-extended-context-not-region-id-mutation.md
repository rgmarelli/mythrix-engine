# ADR-019 — A hotspot's widened context is a second, additive context-object field, never a `region_id` mutation

- **Status**: Accepted
- **Date**: 2026-07-30
- **Realized by**: `agent/context.py::AgentContext.extended_region_id`/`extended_locator`, `agent/turn_service.py::stream_chat_turn`

## Context

The web viewer's Add Context action (`specs/retrieval/context-expansion.md`) lets a user widen a hotspot's displayed reading context past its original, match-derived span. Until now this state lived and died in the detail panel component alone — it was never sent to the backend, so the conversational agent's `/summarize` command and its own context description always scoped to the hotspot's original, narrower `region_id`, regardless of how much context the user had visibly loaded on screen (`specs/tmp/hotspot-context-expansion-agent`).

The natural-looking fix — once the widened window is computed server-side (`GET /api/regions/extend-context`, `specs/retrieval/context-expansion.md` FR-CE-13) — is to have the browser simply send the widened coordinate as the turn's `region_id`, in place of the hotspot's own. This turns out to conflict with two things `region_id` is already load-bearing for:

1. **Thread-reset detection** (`agent/context.py::detect_thread_reset`, FR-AG-16): a changed `region_id` is exactly what starts a new agent thread, discarding conversation history. Widening context around the *same* hotspot is explicitly not "selecting a different hotspot" — FR-AG-16 already carves that distinction out for session-scoped facet fields; the same distinction has to hold for context expansion, and overwriting `region_id` would fire a reset on every single Add Context click.
2. **Hotspot identity in the web viewer** (`web/src/state/useTabs.ts`): `selectedRegionId` is the key `rankedHotspots`/`augmentations`/the detail panel's own remount key are all indexed by, and all of those always carry the *original* query-result region IDs. Overwriting the selection with a widened, recomputed `region_id` would make the "selected" hotspot vanish from its own list on the next render — a de-selection bug, not a display refinement.

## Decision

`AgentContext` (`agent/context.py`) gains two fields, additive to the existing `region_id`/`locator`:

```python
extended_region_id: str | None = None
extended_locator: str | None = None
```

They follow `region_id`/`locator`'s existing "always taken from the incoming turn as-is, even when `None`" rule in `apply_ui_selection` — absence is itself meaningful, the same way "no hotspot selected" is. They are deliberately **excluded** from `detect_thread_reset`'s comparison: only `region_id` and the session-scoped entity fields participate in that check, unchanged.

The two new fields are consulted at exactly the two places text is actually pulled for the LLM, and nowhere else:

- `agent/turn_service.py::stream_chat_turn` passes `region_id=context.extended_region_id or context.region_id` into the graph run — the sole input `/summarize`'s deterministic node (`agent/graph/nodes/summary.py`) reads to decide what passage to fetch.
- `agent/context.py::render_context_summary` substitutes the widened coordinate/locator *in place of* the base ones, in the exact same two-line summary the prompt already had — no added sentence, no new rule the model has to learn — so the model's own `read_region`/`fetch_segments` tool calls reach for the wider span too, without growing the prompt (ADR-009's minimal-prompt rule).

`region_id`/`locator` themselves are never overwritten by this feature. They remain the hotspot's sole identity for thread-reset comparison, `visible_regions` correlation, and every other existing consumer.

## Consequences

- Widening a hotspot's context never resets the active agent thread, and never desynchronizes the web viewer's hotspot-selection bookkeeping — both continue to operate exactly as they did before this feature existed, since neither one's input has changed shape.
- A turn that never used Add Context carries both new fields as `None` throughout, so this feature has zero behavioral effect until a user actually widens a hotspot's context.
- Any future consumer of "the text currently in view for the active hotspot" (not just `/summarize`) needs to apply the same `extended_region_id or region_id` fallback itself; this is not centralized into a single derived field on `AgentContext`, since the two callers that need it (`stream_chat_turn`, `render_context_summary`) are the entirety of the LLM-facing surface today, and a shared derived field would be dead machinery until a third consumer appears (frontend fixed).

## Alternatives considered

- **Overwrite `region_id`/`locator` directly with the widened coordinate.** Rejected — see Context: it corrupts `detect_thread_reset` and the web viewer's hotspot-identity bookkeeping, and is not actually simpler to implement, since it still requires new state somewhere to distinguish "the hotspot's own identity" from "the currently loaded window" — exactly what the two additive fields name explicitly instead of leaving implicit.
- **Have the frontend forward its own client-computed ordinal bounds, with no backend endpoint at all.** Rejected as the shortcut it is: it would leave the boundary rules (section-crossing, source-edge detection) duplicated in TypeScript, and would require `/summarize`'s scope resolution to trust a client-supplied range as authoritative — breaking the trust boundary `read_region`/`fetch_segments` already enforce (both re-derive their range strictly from a `region_id` the backend itself produced, never from a caller's claimed coordinates).
