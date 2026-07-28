"""Composes one full `POST /api/agent` turn out of the existing agent primitives: thread-reset detection
(`agent/context.py`), the LangGraph turn driver (`agent/runner.py`), card
building (`agent/cards.py`), and citation validation
(`core/synthesis/citations.py`). `api/routes.py`'s handler is a
thin wrapper around `run_chat_turn`, matching every existing route's
thinness."""

from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_core.messages import ToolMessage
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from mythrix.agent.adhoc_query import is_adhoc_command
from mythrix.agent.cards import build_cards
from mythrix.agent.context import (
    AgentContext,
    AgentUiSelection,
    apply_ui_selection,
    backfill_from_tool_results,
    detect_thread_reset,
    render_context_summary,
)
from mythrix.agent.runner import run_turn
from mythrix.agent.sessions import SessionStore
from mythrix.core.errors import CitationValidationError, MythrixError
from mythrix.core.logging_config import truncate
from mythrix.core.synthesis.citations import find_invalid_markers, strip_markers

logger = logging.getLogger(__name__)

_SESSION_SCOPED_RESET_FIELDS = ("semiotic_system", "sign", "tradition")
_TOOL_FAILURE_MESSAGE = (
    "I hit a problem reaching one of Mythrix's own tools just now — try again, or rephrase the request."
)
_CITATION_FAILURE_MESSAGE = (
    "I drafted a reply but it referenced something I couldn't actually back up with a tool result, "
    "so I'm not showing it. Could you ask again, maybe more specifically?"
)
_SUMMARIZE_PREFIX = "/summarize"


def _rewrite_summarize_command(message: str, context: AgentContext) -> str | None:
    """Returns a rewritten directive if `message` is a `/summarize` composer
    command, else `None`. Detected before the agent loop runs (`run_turn`,
    below) so the model always sees an explicit instruction rather than
    inferring intent from a bare command."""
    head, _, rest = message.strip().partition(" ")
    if head.lower() != _SUMMARIZE_PREFIX:
        return None
    focus = rest.strip()

    if not context.region_id:
        return (
            "The user typed /summarize but no hotspot is currently selected in the UI. "
            "Tell them to select a passage first; do not call any tools."
        )

    target = context.locator or context.region_id
    directive = f"Use the summarize_passage tool to summarize the active passage ({target})."
    if focus:
        directive += f" Focus specifically on: {focus}."
    elif context.interpretant:
        directive += f" Focus on the interpretant: {context.interpretant}."
    directive += (
        " If you don't already have this passage's text from earlier in this thread, "
        "call fetch_segments first to retrieve it, then call summarize_passage."
    )
    return directive


class AgentCard(BaseModel):
    type: Literal["citation", "interpretant_chips"]
    source_label: str | None = None
    locator: str | None = None
    text: str | None = None
    chips: list[dict] | None = None


class AgentInstruction(BaseModel):
    """A transport-agnostic action for the application to take
    (`specs/interfaces/agnostic-query.md` FR-AQ-07, FR-AQ-13–14) — `payload`
    carries whatever `type` needs; mapping `type` to an actual endpoint call is
    the consumer's job, not this model's or the node's that produced it."""

    type: Literal["confirm_query", "execute_query"]
    payload: dict


class AgentTurnResponse(BaseModel):
    context: AgentContext
    reply_text: str
    cards: list[AgentCard]
    instructions: list[AgentInstruction] = []
    thread_reset: bool


def _safe_json_loads(content: object) -> object:
    try:
        return json.loads(content)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _new_messages(previous_history: list, new_history: list) -> list:
    """`run_turn` returns `previous_history` unchanged (same list object) on
    hitting the recursion bound (FR-RT-05) — no new messages in that case."""
    if new_history is previous_history or len(new_history) <= len(previous_history):
        return []
    return new_history[len(previous_history) :]


def _build_valid_marker_ids(tool_messages: list[ToolMessage]) -> set[str]:
    """Counts citable items across this turn's tool results, in the order
    they appear, per `agent/prompts.py`'s marker convention: each
    `get_sign` citation is a "G" item, each `query_sign`/`fetch_segments`
    segment is an "S" item. Counting continues across multiple tool calls in
    the same turn rather than restarting per call."""
    valid_ids: set[str] = set()
    g_count = 0
    s_count = 0
    for message in tool_messages:
        payload = _safe_json_loads(message.content)
        if message.name == "get_sign" and isinstance(payload, dict) and "error" not in payload:
            for _ in payload.get("citations", ()):
                g_count += 1
                valid_ids.add(f"G{g_count}")
        elif message.name == "query_sign" and isinstance(payload, dict) and "error" not in payload:
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
    logger.info("turn start: session_id=%s message=%s", session_id, truncate(message))
    with sessions.lock_for(session_id):
        previous_context = session.context
        thread_reset = detect_thread_reset(previous_context, ui_selection)
        if thread_reset:
            session.history = []
            session.pending_query = None

        context = apply_ui_selection(previous_context, ui_selection)
        full_context_summary = render_context_summary(context)
        logger.info("resolved context: %s thread_reset=%s", context.model_dump(), thread_reset)

        effective_message = _rewrite_summarize_command(message, context) or message

        def _log_outcome(reply_text: str, tool_calls: list[str], thread_reset: bool) -> None:
            logger.info(
                "turn outcome: reply=%s tool_calls=%s thread_reset=%s",
                truncate(reply_text),
                tool_calls,
                thread_reset,
            )

        try:
            new_history, result = run_turn(
                graph,
                session.history,
                effective_message,
                max_tool_iterations=max_tool_iterations,
                context_summary=full_context_summary,
                pending_query=session.pending_query,
            )
        except MythrixError as exc:
            logger.info("turn failed: tool error: %s", exc)
            session.context = context
            _log_outcome(_TOOL_FAILURE_MESSAGE, [], thread_reset)
            return AgentTurnResponse(
                context=context, reply_text=_TOOL_FAILURE_MESSAGE, cards=[], instructions=[], thread_reset=thread_reset
            )

        session.pending_query = result.pending_query
        instructions = [AgentInstruction(**instruction) for instruction in result.instructions]

        if is_adhoc_command(message):
            # An ad-hoc-query command turn adds nothing to conversation history
            # (agnostic-query.md FR-AQ-16), and its reply is backend-authored, so
            # citation validation — which polices model-authored text (FR-AG-06) —
            # does not apply: a term like "[S1]" would otherwise fail the turn.
            session.context = context
            _log_outcome(result.reply, [], thread_reset)
            return AgentTurnResponse(
                context=context,
                reply_text=result.reply,
                cards=[],
                instructions=instructions,
                thread_reset=thread_reset,
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

        # FIXME: cards disabled — check if we remove Cards from API and Web entirely.
        # cards = _build_cards(tool_messages)
        cards: list[AgentCard] = []
        visible_reply = result.reply.strip()

        valid_ids = _build_valid_marker_ids(tool_messages)
        invalid_markers = find_invalid_markers(visible_reply, valid_ids)
        try:
            if invalid_markers:
                raise CitationValidationError(invalid_markers)
        except CitationValidationError as exc:
            logger.info("turn failed: citation validation: %s", exc)
            session.context = context
            _log_outcome(_CITATION_FAILURE_MESSAGE, result.tool_calls, thread_reset)
            return AgentTurnResponse(
                context=context,
                reply_text=_CITATION_FAILURE_MESSAGE,
                cards=[],
                instructions=[],
                thread_reset=thread_reset,
            )

        session.history = new_messages if model_driven_reset else new_history
        session.context = context

        reply_text = strip_markers(visible_reply)
        _log_outcome(reply_text, result.tool_calls, thread_reset)
        return AgentTurnResponse(
            context=context,
            reply_text=reply_text,
            cards=cards,
            instructions=instructions,
            thread_reset=thread_reset,
        )
