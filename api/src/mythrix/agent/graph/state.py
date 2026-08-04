# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The agent graph's per-turn state shape."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

from mythrix.agent.commands.adhoc import PendingAdhocQuery
from mythrix.agent.commands.augment import PendingAugmentation


class AgentState(TypedDict):
    """`backend_authored` marks a reply with no model-authored text in it, so
    `turn_service.py` can tell an ungrounded citation from a marker-shaped
    sequence the backend or the user's own input put there (FR-AU-31). It is
    a property of the reply, not of the command, so a node sets it per
    reply path.

    `visible_regions` is the consumer's current display, carried in as a
    turn-scoped input (FR-AU-12) — read by the planning node and never read
    back off the final state, like `region_id`/`interpretant`.

    `turn_start_index` (ADR-023) is the index into `messages` where this
    turn's own messages begin — set once by `runner.py::stream_turn`, never
    touched again mid-turn. `validate_citations_node` reads it to find this
    turn's tool messages regardless of how many citation-retry pushback
    messages have since been appended; a naive "scan back to the most recent
    `HumanMessage`" would find its own pushback instead of the turn's real
    boundary once a retry has happened."""

    messages: Annotated[list, add_messages]
    context_summary: str
    pending_query: PendingAdhocQuery | None
    pending_augmentation: PendingAugmentation | None
    instructions: list[dict]
    region_id: str | None
    interpretant: str | None
    visible_regions: list[str]
    backend_authored: bool
    turn_start_index: int
    citation_retry_count: int
