# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The model-driven agent turn: the `agent` node itself, routing around it,
and the deterministic `clarify` node that intercepts a tool result needing
more input before it ever reaches the model (ADR-006)."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.graph import END

from mythrix.agent.graph.state import AgentState
from mythrix.agent.prompts import SYSTEM_PROMPT
from mythrix.core.logging_config import truncate

logger = logging.getLogger(__name__)


def agent_node(state: AgentState, llm_with_tools) -> dict:  # noqa: ANN001 - Runnable, no shared base type worth importing
    """Prepends the system prompt (plus any `context_summary`) fresh on every
    call and invokes the already tool-bound model. `llm_with_tools` is a
    parameter rather than a closure over it, so a test can inject a stub
    tool-calling model with no live Ollama involved — the same pattern
    `summarize_node` uses for its `tools` list."""
    system_text = SYSTEM_PROMPT
    context_summary = state.get("context_summary", "")
    if context_summary:
        system_text = f"{SYSTEM_PROMPT}\n\nCurrent context:\n{context_summary}"
    messages = [SystemMessage(content=system_text), *state["messages"]]
    logger.info(
        "model input: system_prompt=%r history=%s",
        system_text,
        [{"role": type(m).__name__, "content": truncate(str(m.content))} for m in state["messages"]],
    )
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def route_after_agent(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return END


def _safe_json_loads(content: object) -> object:
    try:
        return json.loads(content)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _needs_key(payload: object) -> str | None:
    """The first truthy `needs_*` key in a tool-result payload, if any —
    `get_sign`'s `needs_tradition` is the first (and, in v0, only) case,
    but this is not hardcoded to that one key/tool (agent.md's context object,
    generalized from FR-AG-05/FR-AG-07 by FR-AG-18)."""
    if not isinstance(payload, dict):
        return None
    return next((key for key, value in payload.items() if key.startswith("needs_") and value), None)


def route_after_tools(state: AgentState) -> str:
    """Intercepts any tool result carrying a truthy `needs_*` key — e.g.
    `get_sign`'s `needs_tradition` — before it ever reaches the model
    (FR-AG-18), bypassing the model entirely for a reply that is pure
    formatting rather than synthesis (ADR-006). Every other tool result is
    unaffected and still routes to `agent`."""
    last_message = state["messages"][-1]
    if isinstance(last_message, ToolMessage) and _needs_key(_safe_json_loads(last_message.content)):
        return "clarify"
    return "agent"


def _display(candidate: object) -> str:
    """A candidate's display form: an entity carried as an object is named by
    its `name`, a bare string by itself (ADR-014). Keeps this node generic
    over `needs_*` rather than special-casing traditions."""
    if isinstance(candidate, dict):
        return str(candidate.get("name") or candidate.get("slug", ""))
    return str(candidate)


def clarify_node(state: AgentState) -> dict:
    """Builds the clarifying-question reply directly from the tool result's
    own `needs_*` payload — no model call, so it cannot state anything beyond
    what the tool actually returned. Reads whichever `needs_*` key is
    present; `get_sign`'s `needs_tradition` (candidates under
    `traditions`) is the case exercised today.

    The question is composed from the payload's display keys, so the user is
    asked in the words the viewer shows them, not in slugs (FR-AG-07)."""
    payload = _safe_json_loads(state["messages"][-1].content)
    needs_key = _needs_key(payload)
    field = needs_key.removeprefix("needs_") if needs_key else "value"
    candidates_key = f"{field}s" if not field.endswith("s") else field
    candidates = payload.get(candidates_key, ()) if isinstance(payload, dict) else ()
    sign = payload.get("sign_name") or payload.get("sign", "this sign") if isinstance(payload, dict) else "this sign"
    names = ", ".join(_display(candidate) for candidate in candidates)
    text = f"Which {field} would you like to use for {sign}? Available: {names}."
    return {"messages": [AIMessage(content=text)]}
