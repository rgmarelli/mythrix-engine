"""The agent graph's per-turn state shape."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

from mythrix.agent.commands.adhoc import PendingAdhocQuery


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    context_summary: str
    pending_query: PendingAdhocQuery | None
    instructions: list[dict]
    region_id: str | None
    interpretant: str | None
