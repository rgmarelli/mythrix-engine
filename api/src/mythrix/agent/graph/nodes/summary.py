"""Deterministic node for the `/summarize` command (agent.md
FR-AG-33–FR-AG-36, ADR-012)."""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, ToolMessage

from mythrix.agent.commands.summarize import NO_HOTSPOT_MESSAGE, concepts_for, focus_of, resolve_hotspot
from mythrix.agent.graph.nodes.adhoc import adhoc_reply
from mythrix.agent.graph.state import AgentState


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
        return adhoc_reply(NO_HOTSPOT_MESSAGE, pending)

    try:
        source_id, start_ordinal, end_ordinal = resolve_hotspot(region_id)
    except ValueError:
        return adhoc_reply("Couldn't resolve the selected passage — try reselecting it.", pending)

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
