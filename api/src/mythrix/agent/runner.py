"""UI-free turn driver — streams one compiled agent graph through one turn
and returns updated history plus a `TurnResult`. Kept terminal-free so it is
testable without stdin and reusable by a future non-CLI surface (e.g.
`POST /api/agent`)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from langgraph.graph.state import CompiledStateGraph

from mythrix.core.logging_config import truncate

logger = logging.getLogger(__name__)

_RECURSION_LIMIT_MESSAGE = (
    "I reached this turn's tool-call limit before finishing — try breaking the request into smaller steps."
)


@dataclass
class TurnResult:
    reply: str
    tool_calls: list[str]


def run_turn(
    graph: CompiledStateGraph,
    history: list,
    user_text: str,
    *,
    max_tool_iterations: int,
    context_summary: str = "",
) -> tuple[list, TurnResult]:
    """Runs one turn: appends `user_text` to `history`, streams the graph,
    and returns the updated history plus the ordered tool-name trace
    (specs/interfaces/agent.md FR-AG-10) and reply. On hitting the per-turn tool-call bound (FR-AG-12), the
    turn ends with a clear message and `history` is returned unchanged — the
    runaway turn's messages are not kept.

    `context_summary` (default `""`) is folded into the model invocation by
    `agent/graph.py::agent_node`, alongside `state["messages"]`."""
    messages = [*history, HumanMessage(content=user_text)]
    tool_calls: list[str] = []
    final_state = {"messages": messages}
    logged_upto = len(messages)

    try:
        for state in graph.stream(
            {"messages": messages, "context_summary": context_summary},
            config={"recursion_limit": max_tool_iterations},
            stream_mode="values",
        ):
            final_state = state
            last_message = state["messages"][-1]

            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                tool_calls.extend(call["name"] for call in last_message.tool_calls)

            for new_message in state["messages"][logged_upto:]:
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
            logged_upto = len(state["messages"])
    except GraphRecursionError:
        logger.info(
            "turn hit recursion bound: max_tool_iterations=%d tool_calls=%d", max_tool_iterations, len(tool_calls)
        )
        return history, TurnResult(reply=_RECURSION_LIMIT_MESSAGE, tool_calls=tool_calls)

    new_history = final_state["messages"]
    return new_history, TurnResult(reply=str(new_history[-1].content), tool_calls=tool_calls)
