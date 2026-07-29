# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `agent/graph/builder.py`: `route_input` dispatch and
`compile_agent_graph` assembly, driven end to end with a stub tool-calling
model — no live Ollama — which this module accepts directly: construction
lives in `api/dependencies.py`, not here."""

import pytest
from graph_helpers import compile_graph
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError

from mythrix.agent.graph.builder import route_input
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


@tool
def summarize_passage(passage_text: str, concepts: list[str]) -> dict:
    """Fake summarize_passage mirroring the real tool's shape."""
    return {"summary": f"Summary of: {passage_text} ({', '.join(concepts)})"}


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


def test_route_input_dispatches_the_two_adhoc_commands_and_nothing_else() -> None:
    assert route_input({"messages": [HumanMessage(content="/query laughter")]}) == "parse_query"
    assert route_input({"messages": [HumanMessage(content="/query-confirm 7f3a1c9e")]}) == "execute_query"
    assert route_input({"messages": [HumanMessage(content="tell me about The Tower")]}) == "agent"


def test_route_input_dispatches_summarize() -> None:
    assert route_input({"messages": [HumanMessage(content="/summarize")]}) == "summarize"
    assert route_input({"messages": [HumanMessage(content="/summarize focus on fire")]}) == "summarize"
    assert route_input({"messages": [HumanMessage(content="/summarized")]}) == "agent"


def test_route_input_dispatches_the_two_augmentation_commands() -> None:
    assert route_input({"messages": [HumanMessage(content="/augment where is joy")]}) == "plan_augment"
    assert route_input({"messages": [HumanMessage(content="/augment-confirm 7f3a1c")]}) == "run_augment"
    assert route_input({"messages": [HumanMessage(content="/augmented")]}) == "agent"


def test_compiled_graph_runs_the_tool_and_terminates() -> None:
    graph = compile_graph(ScriptedLLM(), [echo])

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
    graph = compile_graph(LoopingLLM(), [echo])

    with pytest.raises(GraphRecursionError):
        for _ in graph.stream(
            {"messages": [HumanMessage(content="go")]}, config={"recursion_limit": 3}, stream_mode="values"
        ):
            pass


def test_adhoc_commands_never_reach_the_model() -> None:
    """FR-AQ-01 as a structural property: a model that raises on invocation
    proves the command path never consults one."""

    class ExplodingLLM:
        def invoke(self, messages: list) -> AIMessage:
            raise AssertionError("model was invoked for an ad-hoc command turn")

    graph = compile_graph(ExplodingLLM(), [echo])
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

    graph = compile_graph(FabricatingLLM(), [get_sign])
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


def test_summarize_command_never_reaches_the_model() -> None:
    """FR-AG-33 as a structural property, mirroring
    `test_adhoc_commands_never_reach_the_model`."""

    class ExplodingLLM:
        def invoke(self, messages: list) -> AIMessage:
            raise AssertionError("model was invoked for a /summarize turn")

    graph = compile_graph(ExplodingLLM(), _SUMMARIZE_TOOLS)
    final_state = None
    for state in graph.stream(
        {"messages": [HumanMessage(content="/summarize")], "region_id": "waite::0-1", "interpretant": None},
        config={"recursion_limit": 8},
        stream_mode="values",
    ):
        final_state = state

    assert "Summary of" in final_state["messages"][-1].content


@tool
def read_region(region_id: str) -> dict:
    """Fake read_region mirroring the real tool's shape."""
    return {
        "region_id": region_id,
        "source": "Douay-Rheims",
        "source_id": "waite",
        "locator": "Genesis 21:6",
        "text": "God hath made a laughter for me.",
    }


@tool
def augment_passage(passage_text: str, focus: str) -> dict:
    """Fake augment_passage mirroring the real tool's shape."""
    return {"augmentation": f"reading for {focus}"}


@tool
def consolidate_augmentations(focus: str, augmentations: list[dict]) -> dict:
    """Fake consolidate_augmentations mirroring the real tool's shape."""
    return {"consolidation": "Joy recurs [R1]."}


_AUGMENT_NODE_TOOLS = [read_region, augment_passage, consolidate_augmentations]


class ExplodingLLM:
    def invoke(self, messages: list) -> AIMessage:
        raise AssertionError("model was invoked for a deterministic command turn")


def test_the_augmentation_commands_never_reach_the_model() -> None:
    """FR-AU-10 as a structural property, mirroring
    `test_adhoc_commands_never_reach_the_model` — across both turns of the
    gated flow."""
    graph = compile_graph(ExplodingLLM(), _SUMMARIZE_TOOLS, node_tools=_AUGMENT_NODE_TOOLS)

    plan_state = None
    for state in graph.stream(
        {"messages": [HumanMessage(content="/augment where is joy")], "visible_regions": ["waite::0-1"]},
        config={"recursion_limit": 8},
        stream_mode="values",
    ):
        plan_state = state

    pending = plan_state["pending_augmentation"]
    assert pending.focus == "where is joy"
    assert pending.region_ids == ("waite::0-1",)

    run_state = None
    for state in graph.stream(
        {
            "messages": [HumanMessage(content=f"/augment-confirm {pending.id}")],
            "pending_augmentation": pending,
        },
        config={"recursion_limit": 8},
        stream_mode="values",
    ):
        run_state = state

    reply = run_state["messages"][-1].content
    assert reply.startswith("Joy recurs [R1].")
    assert "Augmented 1 region on screen." in reply
    # FR-AU-24: the reading went to its own region, not into the reply.
    assert "reading for where is joy" not in reply


def test_node_only_tools_are_absent_from_the_models_tool_node() -> None:
    """FR-AU-11: `ToolNode` executes `model_tools` alone, so a model that
    somehow named `read_region` could not have it run."""
    graph = compile_graph(ScriptedLLM(), _SUMMARIZE_TOOLS, node_tools=_AUGMENT_NODE_TOOLS)

    tool_node_names = {t.name for t in graph.nodes["tools"].bound.tools_by_name.values()}

    assert tool_node_names == {"fetch_segments", "summarize_passage"}
