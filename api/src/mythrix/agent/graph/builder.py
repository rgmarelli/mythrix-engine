"""Assembles the agent's LangGraph state machine (ADR-006): an `agent` node
bound to a fixed read-only tool set, looping through a `tools` node until the
model answers without a further tool call.

This module takes the tool-bound model as an argument and never constructs
one — `api/dependencies.py` builds a single chat model via
`core/ollama.py::create_chat_model` and derives both roles from it: the
tool-bound binding compiled in here, and the narrow `ChatClient` the
`summarize_passage` tool uses. Keeping construction out of this module is what
keeps the daemon validated once per process while leaving the two roles
distinct.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from mythrix.agent import commands
from mythrix.agent.graph.nodes.adhoc import execute_query_node, parse_query_node
from mythrix.agent.graph.nodes.discover import plan_discovery_node, run_discovery_node
from mythrix.agent.graph.nodes.llm import agent_node, clarify_node, route_after_agent, route_after_tools
from mythrix.agent.graph.nodes.summary import summarize_node
from mythrix.agent.graph.state import AgentState
from mythrix.agent.tools import ToolSet


def route_input(state: AgentState) -> str:
    """Dispatches the turn's incoming message: the two ad-hoc-query commands
    (specs/interfaces/agnostic-query.md FR-AQ-01, FR-AQ-08), `/summarize`
    (agent.md FR-AG-33, ADR-012) and the two discovery commands
    (discovery.md FR-DS-09, ADR-015) go to their own deterministic nodes,
    everything else to the model. This is the only place command dispatch
    happens."""
    message_text = str(state["messages"][-1].content)
    command = commands.resolve_command(message_text)
    if command == commands.adhoc.CONFIRM_COMMAND:
        return "execute_query"
    if command == commands.adhoc.QUERY_COMMAND:
        return "parse_query"
    if command == commands.summarize.SUMMARIZE_COMMAND:
        return "summarize"
    if command == commands.discover.DISCOVER_COMMAND:
        return "plan_discovery"
    if command == commands.discover.DISCOVER_CONFIRM_COMMAND:
        return "run_discovery"
    return "agent"


def compile_agent_graph(  # noqa: ANN001 - Runnable, no shared base type worth importing
    llm_with_tools,
    toolset: ToolSet,
    *,
    discover_max_regions: int,
) -> CompiledStateGraph:
    """Compiles the turn's state machine given an already tool-bound chat
    model. `route_input` dispatches the incoming message: an ad-hoc-query
    command goes to `parse_query`/`execute_query`, `/summarize` goes to
    `summarize`, and a discovery command goes to
    `plan_discovery`/`run_discovery` (ADR-012, ADR-015) — each straight on to
    `END`, reaching neither the model nor `ToolNode` (agnostic-query.md
    FR-AQ-01; agent.md FR-AG-33; discovery.md FR-DS-09);
    everything else goes to `agent`. `agent` (system prompt prepended fresh on
    every call, alongside any `context_summary`) routes to `tools` (a
    `ToolNode` over the fixed read-only tool set) whenever the model's response
    carries tool calls, and back to `agent` afterward — except for a tool
    result carrying a truthy `needs_*` key, which routes to `clarify` instead
    (agent.md FR-AG-18) and straight on to `END`. Ends at `END` once the model
    answers without calling a tool.

    `llm_with_tools` is already bound, so a test can inject a stub
    tool-calling model with no live Ollama involved. It is bound to
    `toolset.model_tools` alone, which is also what `ToolNode` executes;
    `toolset.node_tools` is reachable only by the deterministic nodes' name
    lookup, so ad-hoc retrieval is absent from the model's tool schema
    (FR-DS-10, ADR-015).

    The per-turn tool-call bound (FR-AG-12) is a runtime concern, not a
    compile-time one — `runner.run_turn` applies it via LangGraph's
    `recursion_limit` when it invokes the compiled graph, so a single
    compiled graph is reusable across turns with no reconstruction.
    `discover_max_regions` is not that bound and does not substitute for it:
    it bounds a deterministic node's own generation fan-out, on a path the
    model's tool loop never enters (FR-DS-18)."""
    builder = StateGraph(AgentState)
    builder.add_node("agent", lambda state: agent_node(state, llm_with_tools))
    builder.add_node("tools", ToolNode(toolset.model_tools))
    builder.add_node("clarify", clarify_node)
    builder.add_node("parse_query", parse_query_node)
    builder.add_node("execute_query", execute_query_node)
    builder.add_node("summarize", lambda state: summarize_node(state, toolset.all))
    builder.add_node("plan_discovery", lambda state: plan_discovery_node(state, max_regions=discover_max_regions))
    builder.add_node(
        "run_discovery", lambda state: run_discovery_node(state, toolset.all, max_regions=discover_max_regions)
    )
    builder.add_conditional_edges(
        START,
        route_input,
        {
            "parse_query": "parse_query",
            "execute_query": "execute_query",
            "summarize": "summarize",
            "plan_discovery": "plan_discovery",
            "run_discovery": "run_discovery",
            "agent": "agent",
        },
    )
    builder.add_edge("parse_query", END)
    builder.add_edge("execute_query", END)
    builder.add_edge("summarize", END)
    builder.add_edge("plan_discovery", END)
    builder.add_edge("run_discovery", END)
    builder.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    builder.add_conditional_edges("tools", route_after_tools, {"agent": "agent", "clarify": "clarify"})
    builder.add_edge("clarify", END)
    return builder.compile()
