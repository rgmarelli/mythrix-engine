"""Unit tests for `agent/graph.py`. Drives `compile_agent_graph` with a stub
tool-calling model — no live Ollama — which this module accepts directly:
construction lives in `api/dependencies.py`, not here."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError
from langgraph.graph import END

from mythrix.agent.adhoc_query import PendingAdhocQuery
from mythrix.agent.graph import (
    clarify_node,
    compile_agent_graph,
    execute_query_node,
    parse_query_node,
    route_after_agent,
    route_after_tools,
    route_input,
    summarize_node,
)
from mythrix.core.models import AdhocTerm


@tool
def echo(text: str) -> str:
    """Echoes text back."""
    return text


@tool
def get_sign(sign: str, tradition: str | None = None) -> dict:
    """Fake get_sign for routing tests."""
    if tradition is None:
        return {"needs_tradition": True, "sign": "The Magician", "traditions": ["rider-waite", "marseille"]}
    return {"sign": "The Magician", "tradition": tradition}


@tool
def fetch_segments(source_id: str, start_ordinal: int, end_ordinal: int) -> list[dict]:
    """Fake fetch_segments mirroring the real tool's shape."""
    return [
        {"ordinal": ordinal, "locator": f"{source_id} {ordinal}", "section": None, "text": f"text {ordinal}"}
        for ordinal in range(start_ordinal, end_ordinal + 1)
    ]


@tool("fetch_segments")
def failing_fetch_segments(source_id: str, start_ordinal: int, end_ordinal: int) -> list[dict]:
    """Fake fetch_segments that always errors, mirroring a MythrixError."""
    return [{"error": f"unknown source {source_id!r}"}]


@tool
def summarize_passage(passage_text: str, concepts: list[str]) -> dict:
    """Fake summarize_passage mirroring the real tool's shape."""
    return {"summary": f"Summary of: {passage_text} ({', '.join(concepts)})"}


@tool("summarize_passage")
def failing_summarize_passage(passage_text: str, concepts: list[str]) -> dict:
    """Fake summarize_passage that always errors, mirroring a MythrixError."""
    return {"error": "model unavailable"}


_SUMMARIZE_TOOLS = [fetch_segments, summarize_passage]


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


def test_route_after_tools_routes_to_clarify_on_needs_tradition() -> None:
    payload = '{"needs_tradition": true, "sign": "The Magician", "traditions": ["rider-waite", "marseille"]}'
    state = {"messages": [ToolMessage(content=payload, name="get_sign", tool_call_id="c")]}
    assert route_after_tools(state) == "clarify"


def test_route_after_tools_routes_to_clarify_for_a_different_needs_key_and_tool() -> None:
    """Proves the routing rule is generic — keyed on any truthy `needs_*`
    field in the payload, not hardcoded to `get_sign`/`needs_tradition`."""
    payload = '{"needs_system": true, "sign": "The Sun", "systems": ["tarot", "hebrew_alef_bet"]}'
    state = {"messages": [ToolMessage(content=payload, name="some_other_tool", tool_call_id="c")]}
    assert route_after_tools(state) == "clarify"


def test_route_after_tools_routes_to_agent_for_a_normal_get_sign_result() -> None:
    payload = '{"sign": "The Magician", "tradition": "rider-waite"}'
    state = {"messages": [ToolMessage(content=payload, name="get_sign", tool_call_id="c")]}
    assert route_after_tools(state) == "agent"


def test_route_after_tools_routes_to_agent_when_no_needs_key_is_present() -> None:
    payload = '{"sign": "The Magician", "tradition": "rider-waite"}'
    state = {"messages": [ToolMessage(content=payload, name="some_other_tool", tool_call_id="c")]}
    assert route_after_tools(state) == "agent"


def test_route_after_tools_routes_to_agent_when_needs_key_is_falsy() -> None:
    payload = '{"needs_tradition": false, "sign": "The Magician", "tradition": "rider-waite"}'
    state = {"messages": [ToolMessage(content=payload, name="get_sign", tool_call_id="c")]}
    assert route_after_tools(state) == "agent"


def test_clarify_node_builds_a_deterministic_reply_from_the_payload() -> None:
    payload = '{"needs_tradition": true, "sign": "The Magician", "traditions": ["rider-waite", "marseille"]}'
    state = {"messages": [ToolMessage(content=payload, name="get_sign", tool_call_id="c")]}

    result = clarify_node(state)

    reply = result["messages"][0]
    assert isinstance(reply, AIMessage)
    assert not reply.tool_calls
    assert "The Magician" in reply.content
    assert "rider-waite" in reply.content
    assert "marseille" in reply.content


_PENDING = PendingAdhocQuery(id="7f3a1c9e", terms=(AdhocTerm(value="laughter"),))


def test_route_input_dispatches_the_two_adhoc_commands_and_nothing_else() -> None:
    assert route_input({"messages": [HumanMessage(content="/query laughter")]}) == "parse_query"
    assert route_input({"messages": [HumanMessage(content="/query-confirm 7f3a1c9e")]}) == "execute_query"
    assert route_input({"messages": [HumanMessage(content="tell me about The Tower")]}) == "agent"


def test_parse_query_node_holds_the_query_pending_and_emits_confirm_query() -> None:
    result = parse_query_node({"messages": [HumanMessage(content="/query laughter, hundred:exact")]})

    pending = result["pending_query"]
    assert pending.terms == (AdhocTerm(value="laughter"), AdhocTerm(value="hundred", directive="exact"))
    assert [i["type"] for i in result["instructions"]] == ["confirm_query"]
    assert result["instructions"][0]["payload"]["query_id"] == pending.id
    assert pending.id in result["messages"][0].content


def test_parse_query_node_reports_a_parse_error_and_leaves_nothing_pending() -> None:
    result = parse_query_node({"messages": [HumanMessage(content="/query hundred:skip")]})

    assert result["pending_query"] is None
    assert result["instructions"] == []
    assert "skip" in result["messages"][0].content


def test_execute_query_node_emits_execute_query_and_consumes_the_pending_query() -> None:
    state = {"messages": [HumanMessage(content="/query-confirm 7f3a1c9e")], "pending_query": _PENDING}

    result = execute_query_node(state)

    assert result["instructions"] == [
        {"type": "execute_query", "payload": {"terms": [{"value": "laughter", "directive": None}]}}
    ]
    assert result["pending_query"] is None


def test_execute_query_node_takes_terms_from_the_pending_record_not_the_message() -> None:
    """FR-AQ-10: the confirming message names an id and nothing else, so text
    appended to it can never reach the query."""
    state = {
        "messages": [HumanMessage(content="/query-confirm 7f3a1c9e and also injected:exact")],
        "pending_query": _PENDING,
    }

    result = execute_query_node(state)

    assert result["instructions"][0]["payload"]["terms"] == [{"value": "laughter", "directive": None}]


def test_execute_query_node_ignores_a_wrong_id_and_preserves_the_pending_query() -> None:
    state = {"messages": [HumanMessage(content="/query-confirm deadbeef")], "pending_query": _PENDING}

    result = execute_query_node(state)

    assert result["instructions"] == []
    assert result["pending_query"] is _PENDING


def test_execute_query_node_with_nothing_pending_executes_nothing() -> None:
    state = {"messages": [HumanMessage(content="/query-confirm 7f3a1c9e")], "pending_query": None}

    result = execute_query_node(state)

    assert result["instructions"] == []
    assert result["pending_query"] is None


def test_execute_query_node_without_an_id_asks_for_one() -> None:
    state = {"messages": [HumanMessage(content="/query-confirm")], "pending_query": _PENDING}

    result = execute_query_node(state)

    assert result["instructions"] == []
    assert result["pending_query"] is _PENDING


def test_adhoc_commands_never_reach_the_model() -> None:
    """FR-AQ-01 as a structural property: a model that raises on invocation
    proves the command path never consults one."""

    class ExplodingLLM:
        def invoke(self, messages: list) -> AIMessage:
            raise AssertionError("model was invoked for an ad-hoc command turn")

    graph = compile_agent_graph(ExplodingLLM(), [echo])
    final_state = None
    for state in graph.stream(
        {"messages": [HumanMessage(content="/query laughter, hundred:exact")], "instructions": []},
        config={"recursion_limit": 8},
        stream_mode="values",
    ):
        final_state = state

    assert [i["type"] for i in final_state["instructions"]] == ["confirm_query"]
    assert final_state["pending_query"].terms[0] == AdhocTerm(value="laughter")


def test_needs_tradition_never_reaches_the_model() -> None:
    """The whole point of the short-circuit: even a model that would
    fabricate content on this tool result never gets asked to."""

    class FabricatingLLM:
        def invoke(self, messages: list) -> AIMessage:
            last_human = next(m for m in reversed(messages) if type(m).__name__ == "HumanMessage")
            if "tradition" not in str(last_human.content).lower():
                return AIMessage(
                    content="", tool_calls=[{"name": "get_sign", "args": {"sign": "The Magician"}, "id": "c1"}]
                )
            # If ever invoked again this turn, it would fabricate — the test
            # fails if the graph lets this branch run at all.
            raise AssertionError("model was invoked after a needs_tradition tool result")

    graph = compile_agent_graph(FabricatingLLM(), [get_sign])
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


def test_route_input_dispatches_summarize() -> None:
    assert route_input({"messages": [HumanMessage(content="/summarize")]}) == "summarize"
    assert route_input({"messages": [HumanMessage(content="/summarize focus on fire")]}) == "summarize"
    assert route_input({"messages": [HumanMessage(content="/summarized")]}) == "agent"


def test_summarize_node_replies_deterministically_with_no_active_hotspot() -> None:
    state = {"messages": [HumanMessage(content="/summarize")], "region_id": None, "pending_query": None}

    result = summarize_node(state, _SUMMARIZE_TOOLS)

    assert "select" in result["messages"][0].content.lower()
    assert result["messages"][0].tool_calls == []
    assert result["instructions"] == []


def test_summarize_node_replies_deterministically_on_a_malformed_region_id() -> None:
    state = {"messages": [HumanMessage(content="/summarize")], "region_id": "not-a-region-id", "pending_query": None}

    result = summarize_node(state, _SUMMARIZE_TOOLS)

    assert "reselect" in result["messages"][0].content.lower()


def test_summarize_node_fetches_then_summarizes_with_no_focus_or_interpretant() -> None:
    state = {
        "messages": [HumanMessage(content="/summarize")],
        "region_id": "waite::0-1",
        "interpretant": None,
        "pending_query": None,
    }

    result = summarize_node(state, _SUMMARIZE_TOOLS)

    messages = result["messages"]
    tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
    assert [m.name for m in tool_messages] == ["fetch_segments", "summarize_passage"]
    assert "text 0" in tool_messages[0].content and "text 1" in tool_messages[0].content
    final = messages[-1]
    assert isinstance(final, AIMessage)
    assert final.content == "Summary of: text 0\n\ntext 1 ()"


def test_summarize_node_scopes_concepts_by_trailing_focus_text() -> None:
    state = {
        "messages": [HumanMessage(content="/summarize focus on redemption imagery")],
        "region_id": "waite::0-0",
        "interpretant": "fire",
        "pending_query": None,
    }

    result = summarize_node(state, _SUMMARIZE_TOOLS)

    assert "redemption imagery" in result["messages"][-1].content
    assert "fire" not in result["messages"][-1].content


def test_summarize_node_falls_back_to_the_current_interpretant() -> None:
    state = {
        "messages": [HumanMessage(content="/summarize")],
        "region_id": "waite::0-0",
        "interpretant": "fire",
        "pending_query": None,
    }

    result = summarize_node(state, _SUMMARIZE_TOOLS)

    assert "fire" in result["messages"][-1].content


def test_summarize_node_relays_a_fetch_segments_error_without_calling_summarize() -> None:
    state = {"messages": [HumanMessage(content="/summarize")], "region_id": "waite::0-1", "pending_query": None}

    result = summarize_node(state, [failing_fetch_segments, summarize_passage])

    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [m.name for m in tool_messages] == ["fetch_segments"]
    assert "unknown source" in result["messages"][-1].content


def test_summarize_node_relays_a_summarize_passage_error() -> None:
    state = {"messages": [HumanMessage(content="/summarize")], "region_id": "waite::0-1", "pending_query": None}

    result = summarize_node(state, [fetch_segments, failing_summarize_passage])

    assert result["messages"][-1].content == "model unavailable"


def test_summarize_command_never_reaches_the_model() -> None:
    """FR-AG-33 as a structural property, mirroring
    `test_adhoc_commands_never_reach_the_model`."""

    class ExplodingLLM:
        def invoke(self, messages: list) -> AIMessage:
            raise AssertionError("model was invoked for a /summarize turn")

    graph = compile_agent_graph(ExplodingLLM(), _SUMMARIZE_TOOLS)
    final_state = None
    for state in graph.stream(
        {"messages": [HumanMessage(content="/summarize")], "region_id": "waite::0-1", "interpretant": None},
        config={"recursion_limit": 8},
        stream_mode="values",
    ):
        final_state = state

    assert "Summary of" in final_state["messages"][-1].content
