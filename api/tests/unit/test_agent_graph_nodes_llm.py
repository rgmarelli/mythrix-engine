"""Unit tests for `agent/graph/nodes/llm.py`: routing around the model-driven
agent turn and the deterministic `clarify_node` (ADR-006, agent.md FR-AG-18)."""

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END

from mythrix.agent.graph.nodes.llm import clarify_node, route_after_agent, route_after_tools


def test_route_after_agent_routes_to_tools_when_tool_calls_present() -> None:
    state = {"messages": [AIMessage(content="", tool_calls=[{"name": "echo", "args": {}, "id": "c"}])]}
    assert route_after_agent(state) == "tools"


def test_route_after_agent_routes_to_end_when_no_tool_calls() -> None:
    state = {"messages": [AIMessage(content="a plain answer")]}
    assert route_after_agent(state) == END


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
