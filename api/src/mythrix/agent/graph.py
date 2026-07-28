"""The agent's LangGraph state machine (ADR-006): an `agent` node bound to a
fixed read-only tool set, looping through a `tools` node until the model
answers without a further tool call.

This module takes the tool-bound model as an argument and never constructs
one — `api/dependencies.py` builds a single chat model via
`core/ollama.py::create_chat_model` and derives both roles from it: the
tool-bound binding compiled in here, and the narrow `ChatClient` the
`summarize_passage` tool uses. Keeping construction out of this module is what
keeps the daemon validated once per process while leaving the two roles
distinct.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from mythrix.agent.adhoc_query import (
    CONFIRM_COMMAND,
    QUERY_COMMAND,
    PendingAdhocQuery,
    command_of,
    confirm_id_of,
    confirm_query_instruction,
    execute_query_instruction,
    new_query_id,
    parse_query_command,
    render_confirmation,
    render_dispatch,
)
from mythrix.agent.prompts import SYSTEM_PROMPT
from mythrix.agent.summarize_command import (
    NO_HOTSPOT_MESSAGE,
    SUMMARIZE_COMMAND,
    concepts_for,
    focus_of,
    resolve_hotspot,
)
from mythrix.agent.summarize_command import command_of as summarize_command_of
from mythrix.core.errors import AdhocQueryValidationError
from mythrix.core.logging_config import truncate

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    context_summary: str
    pending_query: PendingAdhocQuery | None
    instructions: list[dict]
    region_id: str | None
    interpretant: str | None


def route_input(state: AgentState) -> str:
    """Dispatches the turn's incoming message: the two ad-hoc-query commands
    (specs/interfaces/agnostic-query.md FR-AQ-01, FR-AQ-08) and `/summarize`
    (agent.md FR-AG-33, ADR-012) go to their own deterministic nodes,
    everything else to the model. This is the only place command dispatch
    happens."""
    message_text = str(state["messages"][-1].content)
    command = command_of(message_text) or summarize_command_of(message_text)
    if command == CONFIRM_COMMAND:
        return "execute_query"
    if command == QUERY_COMMAND:
        return "parse_query"
    if command == SUMMARIZE_COMMAND:
        return "summarize"
    return "agent"


def _adhoc_reply(text: str, pending: PendingAdhocQuery | None) -> dict:
    return {"messages": [AIMessage(content=text)], "pending_query": pending, "instructions": []}


def parse_query_node(state: AgentState) -> dict:
    """Parses a `/query` command and holds the result pending confirmation
    (FR-AQ-04), replying with the parsed list and the command that runs it.
    Calls no model — like `clarify_node` below, the reply is built entirely
    from what the user supplied. A parse error drops any prior pending query
    so "at most one pending" stays unambiguous (FR-AQ-03, FR-AQ-05)."""
    try:
        terms = parse_query_command(str(state["messages"][-1].content))
    except AdhocQueryValidationError as exc:
        return _adhoc_reply(f"Couldn't parse that query: {exc}", None)
    query_id = new_query_id()
    return {
        "messages": [AIMessage(content=render_confirmation(terms, query_id))],
        "pending_query": PendingAdhocQuery(id=query_id, terms=terms),
        "instructions": [confirm_query_instruction(query_id, terms)],
    }


def execute_query_node(state: AgentState) -> dict:
    """Emits the execution instruction, but only for a `/query-confirm`
    command naming the currently-pending query's id (FR-AQ-09). The terms come
    from the pending record, never from the confirming message (FR-AQ-10), and
    confirming consumes it (FR-AQ-12). An unmatched id leaves the pending
    query in place so a typo does not destroy it (FR-AQ-11)."""
    pending = state.get("pending_query")
    query_id = confirm_id_of(str(state["messages"][-1].content))
    if not query_id:
        return _adhoc_reply(f"Name the query to confirm, e.g. `{CONFIRM_COMMAND} 7f3a1c9e`.", pending)
    if pending is None or pending.id != query_id:
        return _adhoc_reply(
            f"No pending query with id {query_id!r}. Send `{QUERY_COMMAND} <terms>` to start one.", pending
        )
    return {
        "messages": [AIMessage(content=render_dispatch(pending.terms))],
        "pending_query": None,
        "instructions": [execute_query_instruction(pending.terms)],
    }


def _tool_by_name(tools: list, name: str):  # noqa: ANN001, ANN201 - BaseTool, no shared base type worth importing
    return next(t for t in tools if t.name == name)


def summarize_node(state: AgentState, tools: list) -> dict:  # noqa: ANN001 - BaseTool list
    """Handles `/summarize` deterministically (agent.md FR-AG-33–FR-AG-36,
    ADR-012): which tools are called, in what order, and with what
    arguments is decided here from the active hotspot's `region_id` and the
    command's own focus text — never by the model's tool selection. Calls
    the same `fetch_segments`/`summarize_passage` tool objects the model
    would otherwise select (looked up by name from the graph's bound tool
    set), so their `MythrixError`-to-`{"error": ...}` mapping (FR-AG-11) is
    inherited unchanged.

    Fabricates the `AIMessage(tool_calls=...)`/`ToolMessage` pairs a
    model-driven call would have produced, so conversation history, the
    tool trace (FR-AG-10), and citation-marker accounting are unaffected in
    shape — only who decided to call the tool differs.

    Calls no model of its own: the one generative step (the summary text)
    happens inside `summarize_passage`, and its result becomes the reply
    verbatim — the same "pure formatting needs no second model call"
    reasoning `clarify_node` already applies (ADR-006)."""
    pending = state.get("pending_query")
    region_id = state.get("region_id")
    if not region_id:
        return _adhoc_reply(NO_HOTSPOT_MESSAGE, pending)

    try:
        source_id, start_ordinal, end_ordinal = resolve_hotspot(region_id)
    except ValueError:
        return _adhoc_reply("Couldn't resolve the selected passage — try reselecting it.", pending)

    fetch_args = {"source_id": source_id, "start_ordinal": start_ordinal, "end_ordinal": end_ordinal}
    segments = _tool_by_name(tools, "fetch_segments").invoke(fetch_args)
    fetch_messages = [
        AIMessage(content="", tool_calls=[{"name": "fetch_segments", "args": fetch_args, "id": "summarize-fetch"}]),
        ToolMessage(content=json.dumps(segments), name="fetch_segments", tool_call_id="summarize-fetch"),
    ]

    error = next((seg["error"] for seg in segments if isinstance(seg, dict) and "error" in seg), None)
    if error or not segments:
        text = error or "Couldn't retrieve any text for the selected passage."
        return {"messages": [*fetch_messages, AIMessage(content=text)], "pending_query": pending, "instructions": []}

    passage_text = "\n\n".join(segment["text"] for segment in segments)
    concepts = concepts_for(focus_of(str(state["messages"][-1].content)), state.get("interpretant"))
    summarize_args = {"passage_text": passage_text, "concepts": concepts}
    result = _tool_by_name(tools, "summarize_passage").invoke(summarize_args)
    summarize_messages = [
        AIMessage(
            content="",
            tool_calls=[{"name": "summarize_passage", "args": summarize_args, "id": "summarize-passage"}],
        ),
        ToolMessage(content=json.dumps(result), name="summarize_passage", tool_call_id="summarize-passage"),
    ]
    reply_text = result.get("error") or result["summary"]

    return {
        "messages": [*fetch_messages, *summarize_messages, AIMessage(content=reply_text)],
        "pending_query": pending,
        "instructions": [],
    }


def route_after_agent(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return END


def _safe_json_loads(content: object) -> object:
    try:
        return json.loads(content)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _needs_key(payload: object) -> str | None:
    """The first truthy `needs_*` key in a tool-result payload, if any —
    `get_sign`'s `needs_tradition` is the first (and, in v0, only) case,
    but this is not hardcoded to that one key/tool (agent.md's context object,
    generalized from FR-AG-05/FR-AG-07 by FR-AG-18)."""
    if not isinstance(payload, dict):
        return None
    return next((key for key, value in payload.items() if key.startswith("needs_") and value), None)


def route_after_tools(state: AgentState) -> str:
    """Intercepts any tool result carrying a truthy `needs_*` key — e.g.
    `get_sign`'s `needs_tradition` — before it ever reaches the model
    (FR-AG-18), bypassing the model entirely for a reply that is pure
    formatting rather than synthesis (ADR-006). Every other tool result is
    unaffected and still routes to `agent`."""
    last_message = state["messages"][-1]
    if isinstance(last_message, ToolMessage) and _needs_key(_safe_json_loads(last_message.content)):
        return "clarify"
    return "agent"


def clarify_node(state: AgentState) -> dict:
    """Builds the clarifying-question reply directly from the tool result's
    own `needs_*` payload — no model call, so it cannot state anything beyond
    what the tool actually returned. Reads whichever `needs_*` key is
    present; `get_sign`'s `needs_tradition` (candidates under
    `traditions`) is the case exercised today."""
    payload = _safe_json_loads(state["messages"][-1].content)
    needs_key = _needs_key(payload)
    field = needs_key.removeprefix("needs_") if needs_key else "value"
    candidates_key = f"{field}s" if not field.endswith("s") else field
    candidates = payload.get(candidates_key, ()) if isinstance(payload, dict) else ()
    sign = payload.get("sign", "this sign") if isinstance(payload, dict) else "this sign"
    text = f"Which {field} would you like to use for {sign}? Available: {', '.join(candidates)}."
    return {"messages": [AIMessage(content=text)]}


def compile_agent_graph(llm_with_tools, tools: list) -> CompiledStateGraph:  # noqa: ANN001 - Runnable, no shared base type worth importing
    """Compiles the turn's state machine given an already tool-bound chat
    model. `route_input` dispatches the incoming message: an ad-hoc-query
    command goes to `parse_query`/`execute_query`, and `/summarize` goes to
    `summarize` (ADR-012) — each straight on to `END`, reaching neither the
    model nor `ToolNode` (agnostic-query.md FR-AQ-01; agent.md FR-AG-33);
    everything else goes to `agent`. `agent` (system prompt prepended fresh on
    every call, alongside any `context_summary`) routes to `tools` (a
    `ToolNode` over the fixed read-only tool set) whenever the model's response
    carries tool calls, and back to `agent` afterward — except for a tool
    result carrying a truthy `needs_*` key, which routes to `clarify` instead
    (agent.md FR-AG-18) and straight on to `END`. Ends at `END` once the model
    answers without calling a tool.

    `llm_with_tools` is already bound, so a test can inject a stub
    tool-calling model with no live Ollama involved.

    The per-turn tool-call bound (FR-AG-12) is a runtime concern, not a
    compile-time one — `runner.run_turn` applies it via LangGraph's
    `recursion_limit` when it invokes the compiled graph, so a single
    compiled graph is reusable across turns with no reconstruction."""

    def agent_node(state: AgentState) -> dict:
        system_text = SYSTEM_PROMPT
        context_summary = state.get("context_summary", "")
        if context_summary:
            system_text = f"{SYSTEM_PROMPT}\n\nCurrent context:\n{context_summary}"
        messages = [SystemMessage(content=system_text), *state["messages"]]
        logger.info(
            "model input: system_prompt=%r history=%s",
            system_text,
            [{"role": type(m).__name__, "content": truncate(str(m.content))} for m in state["messages"]],
        )
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("clarify", clarify_node)
    builder.add_node("parse_query", parse_query_node)
    builder.add_node("execute_query", execute_query_node)
    builder.add_node("summarize", lambda state: summarize_node(state, tools))
    builder.add_conditional_edges(
        START,
        route_input,
        {
            "parse_query": "parse_query",
            "execute_query": "execute_query",
            "summarize": "summarize",
            "agent": "agent",
        },
    )
    builder.add_edge("parse_query", END)
    builder.add_edge("execute_query", END)
    builder.add_edge("summarize", END)
    builder.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    builder.add_conditional_edges("tools", route_after_tools, {"agent": "agent", "clarify": "clarify"})
    builder.add_edge("clarify", END)
    return builder.compile()
