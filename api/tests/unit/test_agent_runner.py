"""Unit tests for `agent/runner.py::stream_turn` — the UI-free turn driver.
Drives a real compiled graph (via `compile_agent_graph`) with a stub
tool-calling model, no live Ollama.

Most tests here care only about the turn's outcome, so they drain the stream
through `run_turn`, the same collapse `turn_service` keeps for callers with no
use for progress. `events` is for the ones that care about the sequence."""

import logging

import pytest
from graph_helpers import compile_graph
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from mythrix.agent.runner import TurnResult, stream_turn


def run_turn(*args, **kwargs) -> tuple[list, TurnResult]:
    """`stream_turn` drained to `(history, result)`, discarding progress."""
    result = next(item for item in stream_turn(*args, **kwargs) if isinstance(item, TurnResult))
    return result.history, result


def events(*args, **kwargs) -> tuple[list[dict], TurnResult]:
    """Every payload a node emitted, in order, plus the terminal result."""
    emitted: list[dict] = []
    for item in stream_turn(*args, **kwargs):
        if isinstance(item, TurnResult):
            return emitted, item
        emitted.append(item)
    raise AssertionError("stream_turn ended without a TurnResult")


@tool
def echo(text: str) -> str:
    """Echoes text back."""
    return text


class ScriptedLLM:
    """Calls `echo` once per turn when asked to, then answers plainly once
    the tool has already run this turn (checked via message history, not a
    call counter, so it behaves correctly across multiple turns)."""

    def invoke(self, messages: list) -> AIMessage:
        last_human = next(m for m in reversed(messages) if type(m).__name__ == "HumanMessage")
        already_called_tool = any(type(m).__name__ == "ToolMessage" for m in messages)
        if last_human.content == "call the tool" and not already_called_tool:
            return AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "c"}])
        return AIMessage(content=f"reply to: {last_human.content}")


class LoopingLLM:
    def invoke(self, messages: list) -> AIMessage:
        return AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "cx"}])


class MultiToolLLM:
    """Requests two tool calls in a single model pass, then answers plainly —
    exercises the message-diff loop against a single `ToolNode` step that
    appends more than one `ToolMessage` at once."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, messages: list) -> AIMessage:
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {"name": "echo", "args": {"text": "first"}, "id": "c1"},
                    {"name": "echo", "args": {"text": "second"}, "id": "c2"},
                ],
            )
        return AIMessage(content="done")


def test_run_turn_returns_the_ordered_tool_trace_and_reply() -> None:
    graph = compile_graph(ScriptedLLM(), [echo])
    history: list = []

    history, result = run_turn(graph, history, "call the tool", max_tool_iterations=8)

    assert result.tool_calls == ["echo"]
    assert result.reply == "reply to: call the tool"
    assert len(history) > 0


def test_run_turn_preserves_history_across_two_turns() -> None:
    graph = compile_graph(ScriptedLLM(), [echo])
    history: list = []

    history, first = run_turn(graph, history, "hello", max_tool_iterations=8)
    assert first.tool_calls == []
    assert first.reply == "reply to: hello"

    history_before_second = list(history)
    history, second = run_turn(graph, history, "hello again", max_tool_iterations=8)

    assert second.reply == "reply to: hello again"
    # Everything from the first turn is still present, in order, at the front.
    assert history[: len(history_before_second)] == history_before_second


def test_run_turn_returns_a_clear_message_when_the_tool_budget_is_exceeded() -> None:
    graph = compile_graph(LoopingLLM(), [echo])
    history: list = []

    new_history, result = run_turn(graph, history, "loop forever", max_tool_iterations=3)

    assert new_history == history  # runaway turn's messages are not kept
    assert "limit" in result.reply.lower()


def test_run_turn_logs_model_output_and_tool_result(caplog: pytest.LogCaptureFixture) -> None:
    graph = compile_graph(ScriptedLLM(), [echo])

    with caplog.at_level(logging.INFO, logger="mythrix.agent.runner"):
        run_turn(graph, [], "call the tool", max_tool_iterations=8)

    messages = [record.getMessage() for record in caplog.records]
    assert any("model output" in m and "echo" in m for m in messages)
    assert any("tool result" in m and "hi" in m for m in messages)


def test_run_turn_logs_every_tool_call_from_one_multi_tool_model_pass(caplog: pytest.LogCaptureFixture) -> None:
    graph = compile_graph(MultiToolLLM(), [echo])

    with caplog.at_level(logging.INFO, logger="mythrix.agent.runner"):
        run_turn(graph, [], "call the tools", max_tool_iterations=8)

    messages = [record.getMessage() for record in caplog.records]
    tool_result_lines = [m for m in messages if "tool result" in m]
    assert any("first" in m for m in tool_result_lines)
    assert any("second" in m for m in tool_result_lines)


def test_run_turn_logs_recursion_bound_hit(caplog: pytest.LogCaptureFixture) -> None:
    graph = compile_graph(LoopingLLM(), [echo])

    with caplog.at_level(logging.INFO, logger="mythrix.agent.runner"):
        run_turn(graph, [], "loop forever", max_tool_iterations=3)

    messages = [record.getMessage() for record in caplog.records]
    assert any("recursion bound" in m for m in messages)


def test_run_turn_logs_model_input_for_every_invocation(caplog: pytest.LogCaptureFixture) -> None:
    graph = compile_graph(ScriptedLLM(), [echo])

    with caplog.at_level(logging.INFO, logger="mythrix.agent.graph.nodes.llm"):
        run_turn(graph, [], "call the tool", max_tool_iterations=8, context_summary="Current sign: The Tower.")

    messages = [record.getMessage() for record in caplog.records]
    input_lines = [m for m in messages if m.startswith("model input:")]
    assert len(input_lines) == 2  # one per model pass: the tool-calling pass, then the final reply
    # The full operator system prompt is logged verbatim, not just the appended context.
    assert "Mythrix semiotics expert assistant" in input_lines[0]
    assert "traditions" in input_lines[0]
    assert "The Tower" in input_lines[0]
    assert "call the tool" in input_lines[0]
    # The second invocation's history now also includes the first pass's tool call and result.
    assert "ToolMessage" in input_lines[1]
    assert "hi" in input_lines[1]


def test_run_turn_carries_a_pending_augmentation_into_the_graph_and_back_out() -> None:
    """FR-AU-08: the graph holds no state between turns, so the session's
    outstanding augmentation round-trips through the driver like
    `pending.query`."""
    graph = compile_graph(ScriptedLLM(), [echo])

    _, plan = run_turn(graph, [], "/augment where joy is", max_tool_iterations=8, visible_regions=["src::1-2"])

    assert plan.pending.augmentation is not None
    assert plan.pending.augmentation.focus == "where joy is"
    assert plan.pending.augmentation.region_ids == ("src::1-2",)
    assert plan.backend_authored is True

    _, confirmed = run_turn(
        graph,
        [],
        "/augment-confirm deadbeef",
        max_tool_iterations=8,
        pending=plan.pending,
    )

    assert confirmed.pending.augmentation is plan.pending.augmentation


def test_a_plan_turn_with_nothing_on_screen_holds_no_pending_augmentation() -> None:
    """FR-AU-04: there is nothing to augment, so the turn refuses rather than
    planning a run over an empty list."""
    graph = compile_graph(ScriptedLLM(), [echo])

    _, plan = run_turn(graph, [], "/augment where joy is", max_tool_iterations=8, visible_regions=[])

    assert plan.pending.augmentation is None
    assert "no regions on screen" in plan.reply.lower()


def test_an_ordinary_turn_emits_no_intermediate_payloads() -> None:
    """FR-AU-22: a turn that produces no progress is the terminal result
    alone, so a consumer never has to special-case the common path."""
    emitted, result = events(compile_graph(ScriptedLLM(), [echo]), [], "hello", max_tool_iterations=8)

    assert emitted == []
    assert result.reply == "reply to: hello"


def test_run_turn_reports_an_ordinary_reply_as_model_authored() -> None:
    graph = compile_graph(ScriptedLLM(), [echo])

    _, result = run_turn(graph, [], "hello", max_tool_iterations=8)

    assert result.backend_authored is False


def test_hitting_the_tool_budget_preserves_both_pending_records() -> None:
    graph = compile_graph(LoopingLLM(), [echo])

    _, plan = run_turn(
        compile_graph(ScriptedLLM(), [echo]),
        [],
        "/augment joy",
        max_tool_iterations=8,
        visible_regions=["src::1-2"],
    )
    _, result = run_turn(graph, [], "loop forever", max_tool_iterations=3, pending=plan.pending)

    assert result.pending.augmentation is plan.pending.augmentation
