"""Unit tests for `agent/runner.py::run_turn` — the UI-free turn driver.
Drives a real compiled graph (via `compile_agent_graph`) with a stub
tool-calling model, no live Ollama."""

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from mythrix.agent.graph import compile_agent_graph
from mythrix.agent.runner import run_turn


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


def test_run_turn_returns_the_ordered_tool_trace_and_reply() -> None:
    graph = compile_agent_graph(ScriptedLLM(), [echo])
    history: list = []

    history, result = run_turn(graph, history, "call the tool", max_tool_iterations=8)

    assert result.tool_calls == ["echo"]
    assert result.reply == "reply to: call the tool"
    assert len(history) > 0


def test_run_turn_preserves_history_across_two_turns() -> None:
    graph = compile_agent_graph(ScriptedLLM(), [echo])
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
    graph = compile_agent_graph(LoopingLLM(), [echo])
    history: list = []

    new_history, result = run_turn(graph, history, "loop forever", max_tool_iterations=3)

    assert new_history == history  # runaway turn's messages are not kept
    assert "limit" in result.reply.lower()
