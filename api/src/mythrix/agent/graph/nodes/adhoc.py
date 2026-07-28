"""Deterministic nodes for the `/query` and `/query-confirm` commands
(specs/interfaces/agnostic-query.md FR-AQ-01, FR-AQ-08). Calls no model —
each reply is built entirely from what the user supplied and the pending
query held in state."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from mythrix.agent.commands.adhoc import (
    CONFIRM_COMMAND,
    QUERY_COMMAND,
    PendingAdhocQuery,
    confirm_id_of,
    confirm_query_instruction,
    execute_query_instruction,
    new_query_id,
    parse_query_command,
    render_confirmation,
    render_dispatch,
)
from mythrix.agent.graph.state import AgentState
from mythrix.core.errors import AdhocQueryValidationError


def adhoc_reply(text: str, pending: PendingAdhocQuery | None) -> dict:
    """A deterministic-node reply carrying no instruction — shared by every
    node in this package that replies without dispatching an instruction."""
    return {"messages": [AIMessage(content=text)], "pending_query": pending, "instructions": []}


def parse_query_node(state: AgentState) -> dict:
    """Parses a `/query` command and holds the result pending confirmation
    (FR-AQ-04), replying with the parsed list and the command that runs it.
    Calls no model — like `clarify_node`, the reply is built entirely from
    what the user supplied. A parse error drops any prior pending query so
    "at most one pending" stays unambiguous (FR-AQ-03, FR-AQ-05)."""
    try:
        terms = parse_query_command(str(state["messages"][-1].content))
    except AdhocQueryValidationError as exc:
        return adhoc_reply(f"Couldn't parse that query: {exc}", None)
    query_id = new_query_id()
    return {
        "messages": [AIMessage(content=render_confirmation(terms, query_id))],
        "pending_query": PendingAdhocQuery(id=query_id, terms=terms),
        "instructions": [confirm_query_instruction(query_id, terms)],
    }


def execute_query_node(state: AgentState) -> dict:
    """Emits the execution instruction, but only for a `/query-confirm`
    command naming the currently-pending query's id (FR-AQ-09). The terms come
    from the pending record, never from the confirming message (FR-AQ-10), and
    confirming consumes it (FR-AQ-12). An unmatched id leaves the pending
    query in place so a typo does not destroy it (FR-AQ-11)."""
    pending = state.get("pending_query")
    query_id = confirm_id_of(str(state["messages"][-1].content))
    if not query_id:
        return adhoc_reply(f"Name the query to confirm, e.g. `{CONFIRM_COMMAND} 7f3a1c9e`.", pending)
    if pending is None or pending.id != query_id:
        return adhoc_reply(
            f"No pending query with id {query_id!r}. Send `{QUERY_COMMAND} <terms>` to start one.", pending
        )
    return {
        "messages": [AIMessage(content=render_dispatch(pending.terms))],
        "pending_query": None,
        "instructions": [execute_query_instruction(pending.terms)],
    }
