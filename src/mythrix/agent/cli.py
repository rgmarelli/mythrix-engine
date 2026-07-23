"""The agent's own Typer app and console script (`mythrix-agent`) — a
console script separate from the `mythrix` CLI (spec FR1, FR12). Does not
import or modify `cli/main.py`.

`run_agent` is the testable REPL core: it takes an already-built graph and
injected I/O callables, so a unit test drives it with no Typer/subprocess
machinery and no running Ollama/Kùzu/Chroma. `main` is the thin wrapper that
builds the real stores, chat clients, tools, and graph, then hands off."""

from __future__ import annotations

from collections.abc import Callable

import typer
from langgraph.graph.state import CompiledStateGraph

from mythrix.agent.graph import build_agent_graph
from mythrix.agent.runner import run_turn
from mythrix.agent.tools import build_tools
from mythrix.core.bootstrap import build_stores
from mythrix.core.config import Settings
from mythrix.core.errors import MythrixError
from mythrix.core.synthesis.chain import OllamaChatClient

app = typer.Typer(name="mythrix-agent", help="Conversational operator for Mythrix.")

_EXIT_COMMANDS = {"exit", "quit"}


def run_agent(
    *,
    graph: CompiledStateGraph,
    max_tool_iterations: int,
    read_line: Callable[[], str],
    write: Callable[[str], None],
) -> int:
    """Loops reading requests via `read_line` until `exit`/`quit`/EOF (spec
    FR1); each turn prints its tool trace (spec FR9) then the reply via
    `write`. Conversation history lives only for this call's duration (spec:
    non-goal on cross-restart persistence). Returns a process exit code."""
    history: list = []
    while True:
        try:
            user_text = read_line().strip()
        except EOFError:
            return 0
        except KeyboardInterrupt:
            write("")
            continue

        if not user_text:
            continue
        if user_text.lower() in _EXIT_COMMANDS:
            return 0

        history, result = run_turn(graph, history, user_text, max_tool_iterations=max_tool_iterations)
        if result.tool_calls:
            write("🔧 " + ", ".join(result.tool_calls))
        write(f"Assistant: {result.reply}")


@app.command()
def main() -> None:
    settings = Settings()
    stores = build_stores(settings)
    generation_model = settings.agent_model or settings.generation_model or ""

    try:
        chat_client = OllamaChatClient(
            generation_model=generation_model,
            base_url=settings.ollama_base_url,
            num_ctx=settings.generation_num_ctx,
        )
        tools = build_tools(stores, settings, chat_client)
        graph = build_agent_graph(
            generation_model=generation_model,
            base_url=settings.ollama_base_url,
            num_ctx=settings.generation_num_ctx,
            tools=tools,
        )
    except MythrixError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("Mythrix Operator — type 'exit' to quit.\n")
    exit_code = run_agent(
        graph=graph,
        max_tool_iterations=settings.agent_max_tool_iterations,
        read_line=lambda: input("You: "),
        write=typer.echo,
    )
    raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
