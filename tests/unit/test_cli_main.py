"""Smoke tests for the actual Typer app wiring (T20-T22's `cli/main.py`) — just
`--help` on every command, which exercises real Typer argument parsing without
needing a running Kùzu/Chroma/Ollama."""

from typer.testing import CliRunner

from mythrix.cli.main import app

runner = CliRunner()


def test_root_help_lists_all_three_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "query" in result.output
    assert "load-symbols" in result.output
    assert "load-documents" in result.output


def test_query_help_lists_expected_options() -> None:
    result = runner.invoke(app, ["query", "--help"])

    assert result.exit_code == 0
    for option in ("--symbol", "--tradition", "--top-k", "--facts-only", "--json", "--strict"):
        assert option in result.output


def test_load_symbols_help_lists_expected_options() -> None:
    result = runner.invoke(app, ["load-symbols", "--help"])

    assert result.exit_code == 0
    assert "--dry-run" in result.output
    assert "--json" in result.output


def test_load_documents_help_lists_expected_options() -> None:
    result = runner.invoke(app, ["load-documents", "--help"])

    assert result.exit_code == 0
    for option in ("--tradition", "--source-slug", "--chunk-size", "--chunk-overlap", "--dry-run", "--json"):
        assert option in result.output
