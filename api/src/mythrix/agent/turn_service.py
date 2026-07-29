"""Composes one full `POST /api/agent` turn out of the existing agent primitives: thread-reset detection
(`agent/context.py`), the LangGraph turn driver (`agent/runner.py`), and
citation validation (`agent/citations.py`). `api/routes.py`'s handler is a
thin wrapper around `run_chat_turn`, matching every existing route's
thinness."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import ToolMessage
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from mythrix.agent.capabilities import InstructionType
from mythrix.agent.citations import find_invalid_markers, strip_markers
from mythrix.agent.commands.adhoc import is_adhoc_command
from mythrix.agent.context import (
    AgentContext,
    apply_ui_selection,
    backfill_from_tool_results,
    detect_thread_reset,
    render_context_summary,
)
from mythrix.agent.runner import run_turn
from mythrix.agent.sessions import SessionStore
from mythrix.core.errors import CitationValidationError, MythrixError
from mythrix.core.logging_config import truncate

logger = logging.getLogger(__name__)

_SESSION_SCOPED_RESET_FIELDS = ("semiotic_system", "sign", "tradition")
_TOOL_FAILURE_MESSAGE = (
    "I hit a problem reaching one of Mythrix's own tools just now — try again, or rephrase the request."
)
_CITATION_FAILURE_MESSAGE = (
    "I drafted a reply but it referenced something I couldn't actually back up with a tool result, "
    "so I'm not showing it. Could you ask again, maybe more specifically?"
)


class AgentInstruction(BaseModel):
    """A transport-agnostic action for the application to take
    (`specs/interfaces/agnostic-query.md` FR-AQ-07, FR-AQ-13–14) — `payload`
    carries whatever `type` needs; mapping `type` to an actual endpoint call is
    the consumer's job, not this model's or the node's that produced it."""

    type: InstructionType
    payload: dict


class AgentTurnResponse(BaseModel):
    context: AgentContext
    reply_text: str
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


_LISTING_TOOL_NAMES = frozenset({"list_signs", "list_traditions", "list_semiotic_systems"})


def _only_listing_tools_called(tool_messages: list[ToolMessage]) -> bool:
    """True when every tool call this turn was a plain enumeration with no
    `citations` field to ever back a marker (`tools/list_signs.py` et al.) —
    the one case where a marker the model attaches anyway is a formatting
    slip on real, tool-derived data rather than an ungrounded claim FR-AG-06
    requires rejecting."""
    return bool(tool_messages) and all(message.name in _LISTING_TOOL_NAMES for message in tool_messages)


def _build_valid_marker_ids(tool_messages: list[ToolMessage]) -> set[str]:
    """Counts citable items across this turn's tool results, in the order
    they appear, per `agent/prompts.py`'s marker convention: each
    `get_sign` citation is a "G" item, each `query_sign`/`fetch_segments`
    segment is an "S" item, and each `query_adhoc` region is an "R" item.
    Counting continues across multiple tool calls in the same turn rather than
    restarting per call.

    A discovery run's `query_adhoc` result is already truncated to the regions
    the run reads, so the "R" ids and the report's sections are the same list
    by construction (FR-DS-21)."""
    valid_ids: set[str] = set()
    g_count = 0
    s_count = 0
    r_count = 0
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
        elif message.name == "query_adhoc" and isinstance(payload, dict) and "error" not in payload:
            for _ in payload.get("regions", ()):
                r_count += 1
                valid_ids.add(f"R{r_count}")
        elif message.name == "fetch_segments" and isinstance(payload, list):
            for segment in payload:
                if "error" in segment:
                    continue
                s_count += 1
                valid_ids.add(f"S{s_count}")
    return valid_ids


def _ungrounded_markers(reply: str, tool_messages: list[ToolMessage], backend_authored: bool) -> tuple[str, ...]:
    """The markers in `reply` naming no item this turn's tools returned.

    Empty for a reply with no model-authored text in it (FR-DS-24): a
    marker-shaped sequence there came from the backend's own composition or
    from the user's own input echoed back, neither of which is the ungrounded
    claim FR-AG-06 exists to reject."""
    if backend_authored or _only_listing_tools_called(tool_messages):
        return ()
    return find_invalid_markers(reply, _build_valid_marker_ids(tool_messages))


def run_chat_turn(
    *,
    graph: CompiledStateGraph,
    sessions: SessionStore,
    session_id: str,
    message: str,
    ui_selection: AgentContext,
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
            session.pending_discovery = None

        context = apply_ui_selection(previous_context, ui_selection)
        full_context_summary = render_context_summary(context)
        logger.info("resolved context: %s thread_reset=%s", context.model_dump(), thread_reset)

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
                message,
                max_tool_iterations=max_tool_iterations,
                context_summary=full_context_summary,
                pending_query=session.pending_query,
                pending_discovery=session.pending_discovery,
                region_id=context.region_id,
                interpretant=context.interpretant,
            )
        except MythrixError as exc:
            logger.info("turn failed: tool error: %s", exc)
            session.context = context
            _log_outcome(_TOOL_FAILURE_MESSAGE, [], thread_reset)
            return AgentTurnResponse(
                context=context, reply_text=_TOOL_FAILURE_MESSAGE, instructions=[], thread_reset=thread_reset
            )

        session.pending_query = result.pending_query
        session.pending_discovery = result.pending_discovery
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

        visible_reply = result.reply.strip()

        invalid_markers = _ungrounded_markers(visible_reply, tool_messages, result.backend_authored)
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
            instructions=instructions,
            thread_reset=thread_reset,
        )
