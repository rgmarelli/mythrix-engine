# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The chat panel's structured working memory (specs/interfaces/agent.md FR-AG-17) —
distinct from the raw per-turn message history the generation model already
sees via `AgentState["messages"]`. `AgentContext` is the single class used for
all three roles the one context object of FR-AG-17 plays: what the browser
sends as-is each turn, `turn_service`'s internal working context, and
`api/routes.py`'s response field."""

from __future__ import annotations

import json

from langchain_core.messages import ToolMessage
from pydantic import BaseModel

# Session-scoped fields (specs/interfaces/agent.md FR-AG-17's Context object) whose change
# identifies a different query subject, not just a display filter — these,
# plus a changed `region_id`, are what trigger a thread reset (FR-AG-16).
# `interpretant` and `min_score` are also session-scoped per FR-AG-17, but
# they refine which hotspots are *shown*, not which hotspot the thread is
# actively grounded in, so they do not reset the thread.
_RESET_FIELDS = ("semiotic_system", "sign", "tradition")


class AgentContext(BaseModel):
    """The turn's context object (specs/interfaces/agent.md FR-AG-17). Incoming, it is the
    browser's current UI selection, which the client never pre-clears or diffs
    before sending; outgoing, it is the backend-confirmed context returned
    alongside the reply."""

    semiotic_system: str | None = None
    sign: str | None = None
    tradition: str | None = None
    interpretant: str | None = None
    min_score: float | None = None
    region_id: str | None = None
    locator: str | None = None
    # The active hotspot's widened structural coordinate/citation, once the
    # web viewer's Add Context action has grown it past its match-derived
    # span (`specs/tmp/hotspot-context-expansion-agent`). Absent whenever the
    # user hasn't widened the active hotspot's context. Additive to
    # `region_id`/`locator` rather than a replacement for them: those two
    # remain the hotspot's own identity everywhere else (thread-reset,
    # `visible_regions` correlation) and are never overwritten by this pair.
    extended_region_id: str | None = None
    extended_locator: str | None = None


def detect_thread_reset(previous: AgentContext, incoming: AgentContext) -> bool:
    """`True` if the incoming turn's UI selection no longer matches the
    hotspot/subject the stored context was scoped to (specs/interfaces/agent.md FR-AG-16): a different
    `region_id`, or a different `semiotic_system`/`sign`/`tradition`. Facet
    selection (`interpretant`) and `min_score` changing alone does not reset
    the thread — those narrow which hotspots are displayed, they don't
    change what the active hotspot is.

    `extended_region_id`/`extended_locator` are deliberately excluded from
    this comparison: widening the active hotspot's context is not selecting
    a different hotspot (FR-AG-16), so it must never itself trigger a
    reset."""
    if incoming.region_id != previous.region_id:
        return True
    return any(getattr(incoming, field) != getattr(previous, field) for field in _RESET_FIELDS)


def apply_ui_selection(context: AgentContext, incoming: AgentContext) -> AgentContext:
    """Merges the browser's current UI selection onto the stored context.
    `region_id` and `locator` are always taken from `incoming` as-is, even
    when `None` — "no hotspot selected" is itself meaningful information for
    a thread-scoped field (specs/interfaces/agent.md's "not yet determined" case, FR-AG-18),
    and `locator` (the hotspot's human-readable citation, e.g. "Ecclesiasticus
    43:1-4", FR-AG-21) always describes the same hotspot `region_id` does, so it
    follows the same all-or-nothing rule. `extended_region_id`/`extended_locator`
    follow the identical all-or-nothing rule for the same reason — "no active
    extension" is meaningful the same way "no hotspot selected" is. Every
    other (session-scoped) field only overwrites the stored value when
    `incoming` actually carries one — a `None` there means "the UI hasn't set
    this," not "clear it" (FR-AG-17: session-scoped fields persist across
    hotspot changes until explicitly changed), so a value the agent
    previously resolved from chat alone survives an otherwise-unrelated
    turn."""
    updates = {
        "region_id": incoming.region_id,
        "locator": incoming.locator,
        "extended_region_id": incoming.extended_region_id,
        "extended_locator": incoming.extended_locator,
    }
    for field_name in ("semiotic_system", "sign", "tradition", "interpretant", "min_score"):
        value = getattr(incoming, field_name)
        if value is not None:
            updates[field_name] = value
    return context.model_copy(update=updates)


def _safe_json_loads(content: object) -> object:
    try:
        return json.loads(content)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def backfill_from_tool_results(context: AgentContext, new_messages: list) -> AgentContext:
    """Deterministically fills/updates `sign`/`tradition`/`semiotic_system`
    from this turn's tool calls and results — never from the model's prose
    (ADR-006). No involvement from the generation model in deciding what to
    backfill.

    Values come from a result payload's identity keys, which carry slugs —
    never from the arguments the model supplied for the call, which carry
    whatever wording the user happened to use (ADR-014). This is what makes a
    field the agent resolved from chat and the same field set by the browser's
    picker the same string for the same entity.

    Mapping: `get_sign` (result carries no `needs_tradition`) and `query_sign`
    both backfill from their own result payloads, which identify the entities
    they resolved. `list_traditions`/`list_signs`/`list_semiotic_systems` never
    backfill (discovery only). `fetch_segments`/`summarize_passage` never
    backfill sign/tradition (operate on coordinates/text, not sign identity)."""
    updates: dict[str, str] = {}

    for message in new_messages:
        if not isinstance(message, ToolMessage):
            continue
        if message.name not in ("get_sign", "query_sign"):
            continue

        payload = _safe_json_loads(message.content)
        if not isinstance(payload, dict) or payload.get("needs_tradition"):
            continue

        for field_name in ("sign", "tradition", "semiotic_system"):
            if payload.get(field_name):
                updates[field_name] = payload[field_name]

    if not updates:
        return context
    return context.model_copy(update=updates)


def render_context_summary(context: AgentContext) -> str:
    """Compact text folded into the model's system prompt alongside
    `SYSTEM_PROMPT` (`agent/graph.py::agent_node`) — never persisted into
    `state["messages"]`, matching how `SYSTEM_PROMPT` itself is already
    handled."""
    lines = []
    if context.region_id:
        # `extended_region_id`/`extended_locator` substitute in place of
        # `region_id`/`locator` here rather than adding a sentence of their
        # own (specs/tmp/hotspot-context-expansion-agent) — the prompt's
        # rule count and shape are unchanged; only the value the model sees
        # for "the active hotspot" widens.
        active_region_id = context.extended_region_id or context.region_id
        active_locator = context.extended_locator or context.locator
        lines.append(f"Active hotspot: {active_region_id}.")
        if active_locator:
            lines.append(f"Its human-readable reference is: {active_locator}.")
    if context.sign:
        lines.append(f"Current sign: {context.sign}.")
    if context.tradition:
        lines.append(f"Current tradition: {context.tradition}.")
    if context.semiotic_system:
        lines.append(f"Semiotic system: {context.semiotic_system}.")
    return "\n".join(lines)
