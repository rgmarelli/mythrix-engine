"""The agent graph's per-turn state shape."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

from mythrix.agent.commands.adhoc import PendingAdhocQuery
from mythrix.agent.commands.discover import PendingDiscovery


class AgentState(TypedDict):
    """`backend_authored` marks a reply with no model-authored text in it, so
    `turn_service.py` can tell an ungrounded citation from a marker-shaped
    sequence the backend or the user's own input put there (FR-DS-24). It is
    a property of the reply, not of the command, so a node sets it per
    reply path."""

    messages: Annotated[list, add_messages]
    context_summary: str
    pending_query: PendingAdhocQuery | None
    pending_discovery: PendingDiscovery | None
    instructions: list[dict]
    region_id: str | None
    interpretant: str | None
    backend_authored: bool
