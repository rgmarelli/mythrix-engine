# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Composes one full `POST /api/agent` turn out of the existing agent
primitives: thread-reset detection (`agent/context.py`), the LangGraph turn
driver (`agent/runner.py`), and citation validation (`agent/citations.py`).

A turn is a sequence of events ending in exactly one `TurnEvent` (FR-AU-22),
so a node that does minutes of work can report progress as it goes.
`api/routes.py`'s handler serializes that sequence; `run_chat_turn` collapses
it for callers that only want the end. The collapse is deliberately private —
a published second contract would have to be kept equal to the terminal event,
and nothing would enforce that."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Literal

from langchain_core.messages import ToolMessage
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from mythrix.agent.capabilities import InstructionType
from mythrix.agent.citation_grounding import grounding_ids, only_listing_tools_called
from mythrix.agent.citations import CITATION_FAILURE_MESSAGE, find_invalid_markers, strip_markers
from mythrix.agent.commands import PendingCommands
from mythrix.agent.commands.adhoc import is_adhoc_command
from mythrix.agent.context import (
    AgentContext,
    apply_ui_selection,
    backfill_from_tool_results,
    detect_thread_reset,
    render_context_summary,
)
from mythrix.agent.runner import TurnResult, stream_turn
from mythrix.agent.sessions import SessionStore
from mythrix.core.errors import CitationValidationError, MythrixError
from mythrix.core.logging_config import truncate

logger = logging.getLogger(__name__)

_SESSION_SCOPED_RESET_FIELDS = ("semiotic_system", "sign", "tradition")
_TOOL_FAILURE_MESSAGE = (
    "I hit a problem reaching one of Mythrix's own tools just now — try again, or rephrase the request."
)


class AgentInstruction(BaseModel):
    """A transport-agnostic action for the application to take
    (`specs/interfaces/agnostic-query.md` FR-AQ-07, FR-AQ-13–14) — `payload`
    carries whatever `type` needs; mapping `type` to an actual endpoint call is
    the consumer's job, not this model's or the node's that produced it."""

    type: InstructionType
    payload: dict


class MessageEvent(BaseModel):
    """A chat message delivered mid-turn (FR-AU-23)."""

    event: Literal["message"] = "message"
    text: str


class InstructionEvent(BaseModel):
    """An instruction delivered mid-turn, before the turn's own instructions
    (FR-AU-23)."""

    event: Literal["instruction"] = "instruction"
    instruction: AgentInstruction


class TurnEvent(BaseModel):
    """The turn's terminal event — exactly one per turn, always last."""

    event: Literal["turn"] = "turn"
    context: AgentContext
    reply_text: str
    instructions: list[AgentInstruction] = []
    thread_reset: bool


TurnStreamEvent = MessageEvent | InstructionEvent | TurnEvent


def _safe_json_loads(content: object) -> object:
    try:
        return json.loads(content)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _new_messages(previous_history: list, new_history: list) -> list:
    """`stream_turn` returns `previous_history` unchanged (same list object) on
    hitting the recursion bound (FR-RT-05) — no new messages in that case."""
    if new_history is previous_history or len(new_history) <= len(previous_history):
        return []
    return new_history[len(previous_history) :]


def _build_valid_marker_ids(tool_messages: list[ToolMessage]) -> set[str]:
    """Collects citable items' ids across this turn's tool results:
    `get_sign`/`query_sign`/`fetch_segments`' own opaque `grounding_id`s
    (ADR-022) via `citation_grounding.grounding_ids`, plus each augmented
    region's "R" item, still numbered by supplied position (FR-AU-30) — a
    distinct, position-based id space `citation_grounding` deliberately
    doesn't handle, since only `/augment` produces it.

    An augmentation run's record carries exactly the regions it augmented, so
    the "R" ids and the labels its consolidation may cite are the same list by
    construction (FR-AU-30, FR-AU-36)."""
    valid_ids = grounding_ids(tool_messages)
    r_count = 0
    for message in tool_messages:
        payload = _safe_json_loads(message.content)
        if message.name == "augment_regions" and isinstance(payload, dict):
            # Labelled by supplied position, so a skipped region leaves a gap
            # — the record carries the labels rather than implying them from
            # a count (FR-AU-30).
            for region in payload.get("regions", ()):
                r_count += 1
                valid_ids.add(region.get("label", f"[R{r_count}]").strip("[]"))
    return valid_ids


def _ungrounded_markers(reply: str, tool_messages: list[ToolMessage], backend_authored: bool) -> tuple[str, ...]:
    """The markers in `reply` naming no item this turn's tools returned.

    Empty for a reply with no model-authored text in it (FR-AU-31): a
    marker-shaped sequence there came from the backend's own composition or
    from the user's own input echoed back, neither of which is the ungrounded
    claim FR-AG-06 exists to reject."""
    if backend_authored or only_listing_tools_called(tool_messages):
        return ()
    return find_invalid_markers(reply, _build_valid_marker_ids(tool_messages))


def _node_event(payload: dict) -> TurnStreamEvent | None:
    """One payload a deterministic node wrote through the custom stream, as
    the event a consumer receives. An unrecognized payload is dropped rather
    than forwarded — the node and this function are the only two places the
    shape is known, so an unknown key is a bug, not a message for a
    consumer."""
    if "message" in payload:
        return MessageEvent(text=str(payload["message"]))
    if "instruction" in payload:
        return InstructionEvent(instruction=AgentInstruction(**payload["instruction"]))
    logger.info("dropping unrecognized node event: keys=%s", sorted(payload))
    return None


def stream_chat_turn(
    *,
    graph: CompiledStateGraph,
    sessions: SessionStore,
    session_id: str,
    message: str,
    ui_selection: AgentContext,
    max_tool_iterations: int,
    visible_regions: list[str] | None = None,
) -> Iterator[TurnStreamEvent]:
    """One turn of the in-app chat panel, as the sequence of events it
    produces (FR-AU-22). Always ends in exactly one `TurnEvent`.

    The session lock spans every yield, so two turns for one session cannot
    interleave — and a consumer that abandons the response mid-stream releases
    it through `GeneratorExit` rather than holding it for the process's life."""
    session = sessions.get_or_create(session_id)
    logger.info("turn start: session_id=%s message=%s", session_id, truncate(message))
    with sessions.lock_for(session_id):
        previous_context = session.context
        thread_reset = detect_thread_reset(previous_context, ui_selection)
        if thread_reset:
            session.history = []
            session.pending = PendingCommands()

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

        streamed_instructions: list[AgentInstruction] = []
        result: TurnResult | None = None
        try:
            for item in stream_turn(
                graph,
                session.history,
                message,
                max_tool_iterations=max_tool_iterations,
                context_summary=full_context_summary,
                pending=session.pending,
                # `/summarize` (agent/graph/nodes/summary.py) reads only this
                # one value to decide what passage to fetch — preferring the
                # user's widened context, when present, over the hotspot's
                # own narrower span is the entire fix for that command.
                region_id=context.extended_region_id or context.region_id,
                interpretant=context.interpretant,
                visible_regions=visible_regions or [],
            ):
                if isinstance(item, TurnResult):
                    result = item
                    break
                event = _node_event(item)
                if event is None:
                    continue
                if isinstance(event, InstructionEvent):
                    streamed_instructions.append(event.instruction)
                yield event
        except MythrixError as exc:
            # After the first event the status code is already committed, so a
            # tool failure is reported in-band rather than as a 502 (FR-AU-25).
            logger.info("turn failed: tool error: %s", exc)
            session.context = context
            _log_outcome(_TOOL_FAILURE_MESSAGE, [], thread_reset)
            yield TurnEvent(
                context=context, reply_text=_TOOL_FAILURE_MESSAGE, instructions=[], thread_reset=thread_reset
            )
            return

        assert result is not None, "stream_turn always ends with a TurnResult"
        new_history = result.history

        session.pending = result.pending
        instructions = [AgentInstruction(**instruction) for instruction in result.instructions]

        if is_adhoc_command(message):
            # An ad-hoc-query command turn adds nothing to conversation history
            # (agnostic-query.md FR-AQ-16), and its reply is backend-authored, so
            # citation validation — which polices model-authored text (FR-AG-06) —
            # does not apply: a term like "[S1]" would otherwise fail the turn.
            session.context = context
            _log_outcome(result.reply, [], thread_reset)
            yield TurnEvent(
                context=context,
                reply_text=result.reply,
                instructions=instructions,
                thread_reset=thread_reset,
            )
            return

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
        if invalid_markers:
            logger.info("turn failed: citation validation: %s", CitationValidationError(invalid_markers))
            session.context = context
            _log_outcome(CITATION_FAILURE_MESSAGE, result.tool_calls, thread_reset)
            yield TurnEvent(
                context=context,
                reply_text=CITATION_FAILURE_MESSAGE,
                instructions=[],
                thread_reset=thread_reset,
            )
            return

        session.history = new_messages if model_driven_reset else new_history
        session.context = context

        reply_text = strip_markers(visible_reply)
        _log_outcome(reply_text, result.tool_calls, thread_reset)
        # Instructions already delivered mid-turn are not repeated here — a
        # consumer that applied them as they arrived must not apply them twice.
        yield TurnEvent(
            context=context,
            reply_text=reply_text,
            instructions=[i for i in instructions if i not in streamed_instructions],
            thread_reset=thread_reset,
        )


def run_chat_turn(**kwargs) -> TurnEvent:
    """`stream_chat_turn` collapsed to its terminal event, for a caller with
    no use for progress. Private to this module's own consumers (tests, and
    any future non-streaming surface) rather than a second endpoint."""
    terminal: TurnEvent | None = None
    for event in stream_chat_turn(**kwargs):
        if isinstance(event, TurnEvent):
            terminal = event
    assert terminal is not None, "stream_chat_turn always ends with a TurnEvent"
    return terminal
