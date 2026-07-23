"""Unit tests for `agent/graph.py`. Drives `compile_agent_graph` with a stub
tool-calling model — no live Ollama — since `build_agent_graph` (the only
caller that constructs a real `ChatOllama`) exists precisely so a test can
bypass it."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError
from langgraph.graph import END

from mythrix.agent.graph import clarify_tradition_node, compile_agent_graph, route_after_agent, route_after_tools


@tool
def echo(text: str) -> str:
    """Echoes text back."""
    return text


@tool
def get_symbol(symbol: str, tradition: str | None = None) -> dict:
    """Fake get_symbol for routing tests."""
    if tradition is None:
        return {"needs_tradition": True, "symbol": "The Magician", "traditions": ["rider-waite", "marseille"]}
    return {"sign": "The Magician", "tradition": tradition}


class ScriptedLLM:
    """Emits one tool call, then a plain answer — the minimal two-turn
    tool-calling script a real model would produce."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, messages: list) -> AIMessage:
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "call-1"}])
        return AIMessage(content=f"done: {messages[-1].content}")


class LoopingLLM:
    """Always requests the same tool call — never reaches a plain answer,
    to exercise the recursion bound."""

    def invoke(self, messages: list) -> AIMessage:
        return AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "call-x"}])


def test_route_after_agent_routes_to_tools_when_tool_calls_present() -> None:
    state = {"messages": [AIMessage(content="", tool_calls=[{"name": "echo", "args": {}, "id": "c"}])]}
    assert route_after_agent(state) == "tools"


def test_route_after_agent_routes_to_end_when_no_tool_calls() -> None:
    state = {"messages": [AIMessage(content="a plain answer")]}
    assert route_after_agent(state) == END


def test_compiled_graph_runs_the_tool_and_terminates() -> None:
    graph = compile_agent_graph(ScriptedLLM(), [echo])

    final_state = None
    for state in graph.stream(
        {"messages": [HumanMessage(content="go")]}, config={"recursion_limit": 8}, stream_mode="values"
    ):
        final_state = state

    messages = final_state["messages"]
    tool_messages = [m for m in messages if type(m).__name__ == "ToolMessage"]
    assert len(tool_messages) == 1
    assert tool_messages[0].content == "hi"
    assert messages[-1].content == "done: hi"


def test_compiled_graph_raises_graph_recursion_error_on_runaway_loop() -> None:
    graph = compile_agent_graph(LoopingLLM(), [echo])

    with pytest.raises(GraphRecursionError):
        for _ in graph.stream(
            {"messages": [HumanMessage(content="go")]}, config={"recursion_limit": 3}, stream_mode="values"
        ):
            pass


def test_route_after_tools_routes_to_clarify_tradition_on_needs_tradition() -> None:
    payload = '{"needs_tradition": true, "symbol": "The Magician", "traditions": ["rider-waite", "marseille"]}'
    state = {"messages": [ToolMessage(content=payload, name="get_symbol", tool_call_id="c")]}
    assert route_after_tools(state) == "clarify_tradition"


def test_route_after_tools_routes_to_agent_for_a_normal_get_symbol_result() -> None:
    payload = '{"sign": "The Magician", "tradition": "rider-waite"}'
    state = {"messages": [ToolMessage(content=payload, name="get_symbol", tool_call_id="c")]}
    assert route_after_tools(state) == "agent"


def test_route_after_tools_routes_to_agent_for_a_different_tool() -> None:
    payload = '{"needs_tradition": true}'  # same shape, but not from get_symbol
    state = {"messages": [ToolMessage(content=payload, name="some_other_tool", tool_call_id="c")]}
    assert route_after_tools(state) == "agent"


def test_clarify_tradition_node_builds_a_deterministic_reply_from_the_payload() -> None:
    payload = '{"needs_tradition": true, "symbol": "The Magician", "traditions": ["rider-waite", "marseille"]}'
    state = {"messages": [ToolMessage(content=payload, name="get_symbol", tool_call_id="c")]}

    result = clarify_tradition_node(state)

    reply = result["messages"][0]
    assert isinstance(reply, AIMessage)
    assert not reply.tool_calls
    assert "The Magician" in reply.content
    assert "rider-waite" in reply.content
    assert "marseille" in reply.content


def test_needs_tradition_never_reaches_the_model() -> None:
    """The whole point of the short-circuit: even a model that would
    fabricate content on this tool result never gets asked to."""

    class FabricatingLLM:
        def invoke(self, messages: list) -> AIMessage:
            last_human = next(m for m in reversed(messages) if type(m).__name__ == "HumanMessage")
            if "tradition" not in str(last_human.content).lower():
                return AIMessage(
                    content="", tool_calls=[{"name": "get_symbol", "args": {"symbol": "The Magician"}, "id": "c1"}]
                )
            # If ever invoked again this turn, it would fabricate — the test
            # fails if the graph lets this branch run at all.
            raise AssertionError("model was invoked after a needs_tradition tool result")

    graph = compile_agent_graph(FabricatingLLM(), [get_symbol])
    final_state = None
    for state in graph.stream(
        {"messages": [HumanMessage(content="tell me about The Magician")]},
        config={"recursion_limit": 8},
        stream_mode="values",
    ):
        final_state = state

    reply = final_state["messages"][-1]
    assert isinstance(reply, AIMessage)
    assert "rider-waite" in reply.content and "marseille" in reply.content
