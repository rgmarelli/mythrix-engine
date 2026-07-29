"""UI-free turn driver — streams one compiled agent graph through one turn,
yielding whatever a node emits as it goes and ending with a `TurnResult`. Kept
terminal-free so it is testable without stdin and reusable by any surface."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from langgraph.graph.state import CompiledStateGraph

from mythrix.agent.commands import PendingCommands
from mythrix.core.logging_config import truncate

logger = logging.getLogger(__name__)

_RECURSION_LIMIT_MESSAGE = (
    "I reached this turn's tool-call limit before finishing — try breaking the request into smaller steps."
)


@dataclass
class TurnResult:
    reply: str
    tool_calls: list[str]
    history: list = field(default_factory=list)
    instructions: list[dict] = field(default_factory=list)
    pending: PendingCommands = field(default_factory=PendingCommands)
    backend_authored: bool = False


def stream_turn(
    graph: CompiledStateGraph,
    history: list,
    user_text: str,
    *,
    max_tool_iterations: int,
    context_summary: str = "",
    pending: PendingCommands | None = None,
    region_id: str | None = None,
    interpretant: str | None = None,
    visible_regions: list[str] | None = None,
) -> Iterator[dict | TurnResult]:
    """Runs one turn: appends `user_text` to `history`, streams the graph, and
    yields each node-emitted payload as it arrives, then one final
    `TurnResult` carrying the updated history, the ordered tool-name trace
    (specs/interfaces/agent.md FR-AG-10) and the reply.

    Intermediate yields are the `dict`s a deterministic node writes through
    LangGraph's custom stream (FR-AU-23); a turn whose nodes emit nothing
    yields the `TurnResult` alone. The distinction is by type, so a caller
    never has to inspect a payload to know whether the turn is over.

    On hitting the per-turn tool-call bound (FR-AG-12), the turn ends with a
    clear message and `TurnResult.history` is the history passed in — the
    runaway turn's messages are not kept.

    `context_summary` (default `""`) is folded into the model invocation by
    `graph/nodes/llm.py::agent_node`, alongside `state["messages"]`.

    `pending` (default `None`, treated as an empty `PendingCommands`) carries
    the session's outstanding ad-hoc query and augmentation into the graph's
    two separate state keys and back out on `TurnResult`, since the graph
    holds no state of its own between turns (agnostic-query.md FR-AQ-05;
    augmentation.md FR-AU-08).

    `region_id`/`interpretant`/`visible_regions` (default `None`) carry the
    session's active hotspot and the consumer's current display into the graph
    for the deterministic nodes to read directly — turn-scoped inputs only,
    unlike `pending`, so nothing reads them back off the final state
    (agent.md FR-AG-33; augmentation.md FR-AU-12, ADR-012)."""
    pending = pending or PendingCommands()
    messages = [*history, HumanMessage(content=user_text)]
    tool_calls: list[str] = []
    final_state = {"messages": messages}
    logged_upto = len(messages)

    try:
        for mode, payload in graph.stream(
            {
                "messages": messages,
                "context_summary": context_summary,
                "pending_query": pending.query,
                "pending_augmentation": pending.augmentation,
                "instructions": [],
                "region_id": region_id,
                "interpretant": interpretant,
                "visible_regions": visible_regions or [],
                "backend_authored": False,
            },
            config={"recursion_limit": max_tool_iterations},
            stream_mode=["values", "custom"],
        ):
            if mode == "custom":
                yield payload
                continue

            final_state = payload
            last_message = payload["messages"][-1]

            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                tool_calls.extend(call["name"] for call in last_message.tool_calls)

            for new_message in payload["messages"][logged_upto:]:
                if isinstance(new_message, AIMessage):
                    logger.info(
                        "model output: content=%s tool_calls=%s",
                        truncate(str(new_message.content)),
                        [
                            {"name": call["name"], "args": truncate(str(call["args"]))}
                            for call in new_message.tool_calls
                        ],
                    )
                elif isinstance(new_message, ToolMessage):
                    logger.info("tool result: name=%s result=%s", new_message.name, truncate(str(new_message.content)))
            logged_upto = len(payload["messages"])
    except GraphRecursionError:
        logger.info(
            "turn hit recursion bound: max_tool_iterations=%d tool_calls=%d", max_tool_iterations, len(tool_calls)
        )
        yield TurnResult(
            reply=_RECURSION_LIMIT_MESSAGE,
            tool_calls=tool_calls,
            history=history,
            pending=pending,
        )
        return

    new_history = final_state["messages"]
    yield TurnResult(
        reply=str(new_history[-1].content),
        tool_calls=tool_calls,
        history=new_history,
        instructions=final_state.get("instructions", []),
        pending=PendingCommands(
            query=final_state.get("pending_query"),
            augmentation=final_state.get("pending_augmentation"),
        ),
        backend_authored=bool(final_state.get("backend_authored")),
    )
