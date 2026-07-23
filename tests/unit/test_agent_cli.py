"""Unit tests for `agent/cli.py::run_agent` — the testable REPL core, driven
with an injected graph and I/O callables (no stdin, no Typer/subprocess
machinery, no running Ollama). Also confirms the separate `mythrix-agent`
entrypoint leaves the existing `mythrix` CLI untouched (spec FR12)."""

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from typer.testing import CliRunner

from mythrix.agent.cli import app as agent_app
from mythrix.agent.cli import run_agent
from mythrix.agent.graph import compile_agent_graph
from mythrix.cli.main import app as mythrix_app
from mythrix.core.config import Settings


@tool
def echo(text: str) -> str:
    """Echoes text back."""
    return text


class OneShotLLM:
    def invoke(self, messages: list) -> AIMessage:
        last_human = next(m for m in reversed(messages) if type(m).__name__ == "HumanMessage")
        return AIMessage(content=f"reply to: {last_human.content}")


def _reader(lines: list[str]):  # noqa: ANN201
    iterator = iter(lines)

    def read_line() -> str:
        try:
            return next(iterator)
        except StopIteration:
            raise EOFError from None

    return read_line


def test_run_agent_prints_reply_and_returns_zero_on_exit() -> None:
    graph = compile_agent_graph(OneShotLLM(), [echo])
    written: list[str] = []

    exit_code = run_agent(
        graph=graph, max_tool_iterations=8, read_line=_reader(["hello", "exit"]), write=written.append
    )

    assert exit_code == 0
    assert any("reply to: hello" in line for line in written)


def test_run_agent_prints_tool_trace_when_a_tool_is_called() -> None:
    class ToolCallingLLM:
        def invoke(self, messages: list) -> AIMessage:
            already_called = any(type(m).__name__ == "ToolMessage" for m in messages)
            if already_called:
                return AIMessage(content="done")
            return AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "c"}])

    graph = compile_agent_graph(ToolCallingLLM(), [echo])
    written: list[str] = []

    run_agent(graph=graph, max_tool_iterations=8, read_line=_reader(["go", "exit"]), write=written.append)

    assert any("echo" in line for line in written if line.startswith("🔧"))


def test_run_agent_returns_zero_on_eof_with_no_input() -> None:
    graph = compile_agent_graph(OneShotLLM(), [echo])
    exit_code = run_agent(graph=graph, max_tool_iterations=8, read_line=_reader([]), write=lambda _: None)
    assert exit_code == 0


def test_main_reports_a_clean_error_and_exits_nonzero_when_model_unresolvable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec FR7: no live Ollama needed — an unset `generation_model` fails
    `OllamaChatClient` fast, before any network call, the same path
    `test_synthesis_chain.py` exercises directly. `Settings` is monkeypatched
    to a `tmp_path` store (fresh, empty Kùzu/Chroma — no `.mythrix/` needed)
    with no generation model configured."""

    def fake_settings() -> Settings:
        return Settings(
            kuzu_db_path=tmp_path / "graph.kuzu",
            chroma_persist_dir=tmp_path / "chroma",
            generation_model=None,
            agent_model=None,
        )

    monkeypatch.setattr("mythrix.agent.cli.Settings", fake_settings)

    result = CliRunner().invoke(agent_app)

    assert result.exit_code == 1
    assert "Error" in result.output


def test_mythrix_cli_is_unchanged_by_the_agent_entrypoint() -> None:
    """spec FR12: the agent ships as a separate `mythrix-agent` script and
    adds no command to `mythrix`."""
    result = CliRunner().invoke(mythrix_app, ["--help"])
    assert result.exit_code == 0
    assert "agent" not in result.output.lower().split()
    for command in ("query", "load-symbols", "load-documents"):
        assert command in result.output
