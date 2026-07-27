"""The chat panel's structured working memory (specs/interfaces/agent.md FR-AG-17) —
distinct from the raw per-turn message history the generation model already
sees via `AgentState["messages"]`. `AgentContext` is deliberately the single
class used both as `turn_service`'s internal working context and as
`api/routes.py`'s response field: `AgentUiSelection` (what the browser sends,
as-is, each turn) and `AgentContext` (the backend-confirmed shape) carry the
same fields, so both live here rather than being redefined in `api/routes.py`."""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel

# Session-scoped fields (specs/interfaces/agent.md FR-AG-17's Context object) whose change
# identifies a different query subject, not just a display filter — these,
# plus a changed `region_id`, are what trigger a thread reset (FR-AG-16).
# `source_id`, `interpretant`, and `min_score` are also session-scoped per
# FR-AG-17, but they refine which hotspots are *shown*, not which hotspot the
# thread is actively grounded in, so they do not reset the thread.
_RESET_FIELDS = ("semiotic_system", "sign", "tradition")


class AgentUiSelection(BaseModel):
    """What the browser sends, as-is, each turn (specs/interfaces/agent.md FR-AG-17) — the
    client never pre-clears or diffs this before sending."""

    semiotic_system: str | None = None
    sign: str | None = None
    tradition: str | None = None
    source_id: str | None = None
    interpretant: str | None = None
    min_score: float | None = None
    region_id: str | None = None
    locator: str | None = None


class AgentContext(BaseModel):
    """The backend-confirmed context, returned alongside every turn's reply
    (specs/interfaces/agent.md FR-AG-17)."""

    semiotic_system: str | None = None
    sign: str | None = None
    tradition: str | None = None
    source_id: str | None = None
    interpretant: str | None = None
    min_score: float | None = None
    region_id: str | None = None
    locator: str | None = None


def detect_thread_reset(previous: AgentContext, incoming: AgentUiSelection) -> bool:
    """`True` if the incoming turn's UI selection no longer matches the
    hotspot/subject the stored context was scoped to (specs/interfaces/agent.md FR-AG-16): a different
    `region_id`, or a different `semiotic_system`/`sign`/`tradition`. Facet
    selection (`source_id`/`interpretant`) and `min_score` changing alone
    does not reset the thread — those narrow which hotspots are displayed,
    they don't change what the active hotspot is."""
    if incoming.region_id != previous.region_id:
        return True
    return any(getattr(incoming, field) != getattr(previous, field) for field in _RESET_FIELDS)


def apply_ui_selection(context: AgentContext, incoming: AgentUiSelection) -> AgentContext:
    """Merges the browser's current UI selection onto the stored context.
    `region_id` and `locator` are always taken from `incoming` as-is, even
    when `None` — "no hotspot selected" is itself meaningful information for
    a thread-scoped field (specs/interfaces/agent.md's "not yet determined" case, FR-AG-18),
    and `locator` (the hotspot's human-readable citation, e.g. "Ecclesiasticus
    43:1-4", FR-AG-21) always describes the same hotspot `region_id` does, so it
    follows the same all-or-nothing rule. Every other (session-scoped) field
    only overwrites the stored value when `incoming` actually carries one —
    a `None` there means "the UI hasn't set this," not "clear it" (FR-AG-17:
    session-scoped fields persist across hotspot changes until explicitly
    changed), so a value the agent previously resolved from chat alone
    survives an otherwise-unrelated turn."""
    updates = {"region_id": incoming.region_id, "locator": incoming.locator}
    for field_name in ("semiotic_system", "sign", "tradition", "source_id", "interpretant", "min_score"):
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

    Mapping: `get_sign` (result carries no `needs_tradition`) backfills all
    three fields straight from its own result payload (which already
    includes `sign`/`tradition`/`semiotic_system`). `query_sign` backfills
    `sign`/`tradition` from the *call's own arguments* (its result payload
    carries region/segment data, not sign identity). `list_traditions`/
    `list_signs`/`list_semiotic_systems` never backfill (discovery only).
    `fetch_segments`/`summarize_passage` never backfill sign/tradition
    (operate on coordinates/text, not sign identity)."""
    updates: dict[str, str] = {}
    pending_call_args: dict[str, dict] = {}

    for message in new_messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            for call in message.tool_calls:
                pending_call_args[call["id"]] = call
            continue

        if not isinstance(message, ToolMessage):
            continue

        payload = _safe_json_loads(message.content)
        call = pending_call_args.get(message.tool_call_id)

        if message.name == "get_sign":
            if isinstance(payload, dict) and not payload.get("needs_tradition"):
                if payload.get("sign"):
                    updates["sign"] = payload["sign"]
                if payload.get("tradition"):
                    updates["tradition"] = payload["tradition"]
                if payload.get("semiotic_system"):
                    updates["semiotic_system"] = payload["semiotic_system"]
        elif message.name == "query_sign" and call is not None:
            args = call.get("args", {})
            if args.get("sign"):
                updates["sign"] = args["sign"]
            if args.get("tradition"):
                updates["tradition"] = args["tradition"]

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
        lines.append(f"Active hotspot: {context.region_id}.")
        if context.locator:
            lines.append(f"Its human-readable reference is: {context.locator}.")
    if context.sign:
        subject = context.sign
        if context.tradition:
            subject += f" ({context.tradition})"
        lines.append(f"Current sign: {subject}.")
    if context.semiotic_system:
        lines.append(f"Semiotic system: {context.semiotic_system}.")
    return "\n".join(lines)
