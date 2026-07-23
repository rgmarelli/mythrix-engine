"""The agent's LangGraph state machine — productionizes the scratch
`prueba2.py` agent-node/`ToolNode` loop into a tested, injectable module.

Builds its **own** tool-capable `ChatOllama` here rather than reusing
`core/synthesis/chain.py::OllamaChatClient`, which wraps `ChatOllama` behind a
narrow `invoke(prompt) -> str` with no tool-binding surface. Keeping that
client narrow (it is also used, unchanged, by the `summarize_passage` tool)
and giving the agent node its own construction avoids overloading one class
with two different jobs (plain completion vs. tool-calling). The
"not found"/"can't reach the daemon" message-text matching below mirrors
`OllamaChatClient.__init__`'s empirically-derived mapping (see that module's
docstring) — duplicated rather than factored into `core/`, since this package
is otherwise self-contained from `core/` beyond the read-only
`list_semiotic_systems` addition (`specs/agent-operator/plan.md`).
"""

from __future__ import annotations

import json
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from mythrix.agent.prompts import SYSTEM_PROMPT
from mythrix.core.errors import ModelRequestError, ModelUnavailableError


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def _build_tool_chat_model(*, generation_model: str, base_url: str, num_ctx: int) -> ChatOllama:
    """Constructs the tool-capable chat model, fail-fast (spec FR8) — mirrors
    `OllamaChatClient.__init__`'s message-text error mapping."""
    if not generation_model:
        raise ModelUnavailableError(generation_model or "<unset>")
    try:
        return ChatOllama(
            model=generation_model,
            base_url=base_url,
            temperature=0.15,
            num_ctx=num_ctx,
            validate_model_on_init=True,
        )
    except Exception as exc:  # noqa: BLE001 - validate_model_on_init raises inconsistent exception
        # types across langchain_ollama/httpx versions for "model not found" and
        # "can't reach the daemon at all" alike, so match on message rather than
        # type — same empirically-derived mapping as OllamaChatClient.
        message = str(exc)
        if "not found in Ollama" in message or "Failed to connect to Ollama" in message:
            raise ModelUnavailableError(generation_model) from exc
        raise ModelRequestError(generation_model, cause=f"{type(exc).__name__}: {message}") from exc


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


def route_after_tools(state: AgentState) -> str:
    """Intercepts one specific tool result — `get_symbol`'s `needs_tradition`
    — before it ever reaches the model (spec FR7). Observed live: a tool
    result carrying no interpretive content at all (just a tradition list) is
    still, occasionally, followed by the model composing fabricated
    denotations rather than asking — sampling-dependent, not reliably
    reproduced, so not something a stronger prompt can be trusted to prevent.
    A tradition list needs no model synthesis to relay, so this removes the
    model from the decision instead of asking it more forcefully to behave.
    Every other tool result is unaffected and still routes to `agent`."""
    last_message = state["messages"][-1]
    if isinstance(last_message, ToolMessage) and last_message.name == "get_symbol":
        payload = _safe_json_loads(last_message.content)
        if isinstance(payload, dict) and payload.get("needs_tradition"):
            return "clarify_tradition"
    return "agent"


def clarify_tradition_node(state: AgentState) -> dict:
    """Builds the tradition-choice reply directly from `get_symbol`'s own
    `needs_tradition` payload — no model call, so it cannot state anything
    beyond what the tool actually returned."""
    payload = _safe_json_loads(state["messages"][-1].content)
    traditions = ", ".join(payload.get("traditions", ())) if isinstance(payload, dict) else ""
    symbol = payload.get("symbol", "this symbol") if isinstance(payload, dict) else "this symbol"
    text = f"Which tradition would you like to use for {symbol}? Available: {traditions}."
    return {"messages": [AIMessage(content=text)]}


def compile_agent_graph(llm_with_tools, tools: list) -> CompiledStateGraph:  # noqa: ANN001 - Runnable, no shared base type worth importing
    """Compiles the `agent` ↔ `tools` loop given an already tool-bound chat
    model: `agent` (system prompt prepended fresh on every call) routes to
    `tools` (a `ToolNode` over the fixed read-only tool set) whenever the
    model's response carries tool calls, and back to `agent` afterward — except
    for `get_symbol`'s `needs_tradition` result, which routes to
    `clarify_tradition` instead (spec FR7) and straight on to `END`. Ends at
    `END` once the model answers without calling a tool.

    Kept separate from `build_agent_graph` so a test can inject a stub
    tool-calling model with no live Ollama involved — `build_agent_graph`
    is the only caller that needs a real `ChatOllama`.

    The per-turn tool-call bound (spec FR12) is a runtime concern, not a
    compile-time one — `runner.run_turn` applies it via LangGraph's
    `recursion_limit` when it invokes the compiled graph, so a single
    compiled graph is reusable across turns with no reconstruction."""

    def agent_node(state: AgentState) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("clarify_tradition", clarify_tradition_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    builder.add_conditional_edges(
        "tools", route_after_tools, {"agent": "agent", "clarify_tradition": "clarify_tradition"}
    )
    builder.add_edge("clarify_tradition", END)
    return builder.compile()


def build_agent_graph(*, generation_model: str, base_url: str, num_ctx: int, tools: list) -> CompiledStateGraph:
    """Constructs the real, tool-bound `ChatOllama` (fail-fast, spec FR8) and
    compiles the graph around it. The `mythrix-agent` entrypoint's only call
    into this module."""
    llm_with_tools = _build_tool_chat_model(
        generation_model=generation_model, base_url=base_url, num_ctx=num_ctx
    ).bind_tools(tools)
    return compile_agent_graph(llm_with_tools, tools)
