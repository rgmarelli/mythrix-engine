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
    assert "load-signs" in result.output
    assert "load-documents" in result.output


def test_query_help_lists_expected_options() -> None:
    """--facts-only and --strict are gone (FR-RT-10 — every query is now
    facts-only in shape, and there's no generated citation to be strict
    about); --match-pool is new (FR-RT-08)."""
    result = runner.invoke(app, ["query", "--help"])

    assert result.exit_code == 0
    for option in ("--sign", "--tradition", "--top-k", "--match-pool", "--json"):
        assert option in result.output
    for removed_option in ("--facts-only", "--strict"):
        assert removed_option not in result.output


def test_load_signs_help_lists_expected_options() -> None:
    result = runner.invoke(app, ["load-signs", "--help"])

    assert result.exit_code == 0
    assert "--dry-run" in result.output
    assert "--json" in result.output


def test_load_documents_help_lists_expected_options() -> None:
    """--tradition/--source-slug are gone — a corpus source's id/domain are
    authored in its own colocated YAML, discovered automatically (FR-CO-01)."""
    result = runner.invoke(app, ["load-documents", "--help"])

    assert result.exit_code == 0
    for option in ("--chunk-size", "--chunk-overlap", "--dry-run", "--json"):
        assert option in result.output
    for removed_option in ("--tradition", "--source-slug"):
        assert removed_option not in result.output
