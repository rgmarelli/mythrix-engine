# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""In-graph citation validation with a bounded, corrective retry (ADR-023) —
reached from `route_after_agent` whenever `agent_node` produces a reply with
no further tool calls. Deterministic, like `clarify_node` (ADR-006): it never
calls the model itself, only decides whether to let a reply through, ask the
model to try again, or give up in favor of the same fallback
`turn_service.py` has always used."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END

from mythrix.agent.citation_grounding import grounding_ids, only_listing_tools_called
from mythrix.agent.citations import CITATION_FAILURE_MESSAGE, find_invalid_markers
from mythrix.agent.graph.state import AgentState
from mythrix.agent.prompts import render_citation_pushback


def validate_citations_node(state: AgentState, *, max_retries: int) -> dict:
    """Checks the just-produced reply's markers against this turn's own tool
    results — found via `turn_start_index`, fixed once per turn, rather than
    "the most recent `HumanMessage`", which a prior retry's own pushback
    would otherwise shadow.

    A valid reply, or one where only listing tools were called (nothing to
    cite), is a no-op: the reply already on `state["messages"]` stands, and
    `route_after_citation_check` sends it straight to `END`. An invalid reply
    either gets a pushback naming exactly what was wrong (retries remaining)
    or is replaced with `CITATION_FAILURE_MESSAGE` (retries exhausted) —
    either way, this node's own return is the only state change; it never
    calls the model."""
    reply = state["messages"][-1]
    turn_start_index = state.get("turn_start_index", 0)
    tool_messages = [m for m in state["messages"][turn_start_index:] if isinstance(m, ToolMessage)]
    if only_listing_tools_called(tool_messages):
        return {}

    invalid = find_invalid_markers(str(reply.content), grounding_ids(tool_messages))
    if not invalid:
        return {}

    retries_used = state.get("citation_retry_count", 0)
    if retries_used >= max_retries:
        return {"messages": [AIMessage(content=CITATION_FAILURE_MESSAGE)]}
    return {
        "messages": [HumanMessage(content=render_citation_pushback(invalid))],
        "citation_retry_count": retries_used + 1,
    }


def route_after_citation_check(state: AgentState) -> str:
    """`validate_citations_node`'s only way of asking for another generation
    attempt is a trailing pushback `HumanMessage` — the only other place one
    could appear at this point in the graph is the turn's own original input,
    which this router never sees (a node always runs between the last
    `HumanMessage` and here)."""
    return "agent" if isinstance(state["messages"][-1], HumanMessage) else END
