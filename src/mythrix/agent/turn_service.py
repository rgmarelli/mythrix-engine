"""Composes one full `POST /api/agent` turn out of the existing agent primitives: thread-reset detection
(`agent/context.py`), the LangGraph turn driver (`agent/runner.py`), card
building (`agent/cards.py`), notes splitting (`agent/notes.py`), and citation
validation (`core/synthesis/citations.py`). `api/routes.py`'s handler is a
thin wrapper around `run_chat_turn`, matching every existing route's
thinness."""

from __future__ import annotations

import json
from typing import Literal

from langchain_core.messages import ToolMessage
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from mythrix.agent.cards import build_cards
from mythrix.agent.context import (
    AgentContext,
    AgentUiSelection,
    apply_ui_selection,
    backfill_from_tool_results,
    detect_thread_reset,
    render_context_summary,
)
from mythrix.agent.notes import split_agent_notes, strip_markdown
from mythrix.agent.runner import run_turn
from mythrix.agent.sessions import SessionStore
from mythrix.core.errors import CitationValidationError, MythrixError
from mythrix.core.synthesis.citations import find_invalid_markers, strip_markers

_SESSION_SCOPED_RESET_FIELDS = ("semiotic_system", "sign", "tradition")
_TOOL_FAILURE_MESSAGE = (
    "I hit a problem reaching one of Mythrix's own tools just now — try again, or rephrase the request."
)
_CITATION_FAILURE_MESSAGE = (
    "I drafted a reply but it referenced something I couldn't actually back up with a tool result, "
    "so I'm not showing it. Could you ask again, maybe more specifically?"
)


class AgentCard(BaseModel):
    type: Literal["citation", "interpretant_chips"]
    source_label: str | None = None
    locator: str | None = None
    text: str | None = None
    chips: list[dict] | None = None


class AgentTurnResponse(BaseModel):
    context: AgentContext
    reply_text: str
    cards: list[AgentCard]
    instructions: list[dict] = []
    thread_reset: bool


def _safe_json_loads(content: object) -> object:
    try:
        return json.loads(content)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _new_messages(previous_history: list, new_history: list) -> list:
    """`run_turn` returns `previous_history` unchanged (same list object) on
    hitting the recursion bound (FR13) — no new messages in that case."""
    if new_history is previous_history or len(new_history) <= len(previous_history):
        return []
    return new_history[len(previous_history) :]


def _build_valid_marker_ids(tool_messages: list[ToolMessage]) -> set[str]:
    """Counts citable items across this turn's tool results, in the order
    they appear, per `agent/prompts.py`'s marker convention: each
    `get_symbol` citation is a "G" item, each `query_symbol`/`fetch_segments`
    segment is an "S" item. Counting continues across multiple tool calls in
    the same turn rather than restarting per call."""
    valid_ids: set[str] = set()
    g_count = 0
    s_count = 0
    for message in tool_messages:
        payload = _safe_json_loads(message.content)
        if message.name == "get_symbol" and isinstance(payload, dict) and "error" not in payload:
            for _ in payload.get("citations", ()):
                g_count += 1
                valid_ids.add(f"G{g_count}")
        elif message.name == "query_symbol" and isinstance(payload, dict) and "error" not in payload:
            for region in payload.get("regions", ()):
                for _ in region.get("segments", ()):
                    s_count += 1
                    valid_ids.add(f"S{s_count}")
        elif message.name == "fetch_segments" and isinstance(payload, list):
            for segment in payload:
                if "error" in segment:
                    continue
                s_count += 1
                valid_ids.add(f"S{s_count}")
    return valid_ids


def _build_cards(tool_messages: list[ToolMessage]) -> list[AgentCard]:
    cards: list[dict] = []
    for message in tool_messages:
        payload = _safe_json_loads(message.content)
        cards.extend(build_cards(message.name, payload))
    return [AgentCard(**card) for card in cards]


def run_chat_turn(
    *,
    graph: CompiledStateGraph,
    sessions: SessionStore,
    session_id: str,
    message: str,
    ui_selection: AgentUiSelection,
    max_tool_iterations: int,
) -> AgentTurnResponse:
    session = sessions.get_or_create(session_id)
    with sessions.lock_for(session_id):
        previous_context = session.context
        thread_reset = detect_thread_reset(previous_context, ui_selection)
        if thread_reset:
            session.agent_notes = ""
            session.history = []

        context = apply_ui_selection(previous_context, ui_selection)
        full_context_summary = render_context_summary(context)
        if session.agent_notes:
            note_line = f"Notes from earlier in this thread: {session.agent_notes}"
            full_context_summary = f"{full_context_summary}\n{note_line}" if full_context_summary else note_line

        try:
            new_history, result = run_turn(
                graph,
                session.history,
                message,
                max_tool_iterations=max_tool_iterations,
                context_summary=full_context_summary,
            )
        except MythrixError:
            session.context = context
            return AgentTurnResponse(
                context=context, reply_text=_TOOL_FAILURE_MESSAGE, cards=[], thread_reset=thread_reset
            )

        new_messages = _new_messages(session.history, new_history)
        tool_messages = [m for m in new_messages if isinstance(m, ToolMessage)]
        context = backfill_from_tool_results(context, new_messages)

        def _resolved_differently(field: str) -> bool:
            previous_value = getattr(previous_context, field)
            return previous_value is not None and getattr(context, field) != previous_value

        model_driven_reset = any(_resolved_differently(field) for field in _SESSION_SCOPED_RESET_FIELDS)
        if model_driven_reset:
            thread_reset = True
            session.agent_notes = ""

        cards = _build_cards(tool_messages)
        visible_reply, notes = split_agent_notes(result.reply)
        if notes:
            session.agent_notes = f"{session.agent_notes}\n{notes}".strip() if session.agent_notes else notes

        valid_ids = _build_valid_marker_ids(tool_messages)
        invalid_markers = find_invalid_markers(visible_reply, valid_ids)
        try:
            if invalid_markers:
                raise CitationValidationError(invalid_markers)
        except CitationValidationError:
            session.context = context
            return AgentTurnResponse(
                context=context, reply_text=_CITATION_FAILURE_MESSAGE, cards=[], thread_reset=thread_reset
            )

        session.history = new_messages if model_driven_reset else new_history
        session.context = context

        return AgentTurnResponse(
            context=context,
            reply_text=strip_markdown(strip_markers(visible_reply)),
            cards=cards,
            thread_reset=thread_reset,
        )
