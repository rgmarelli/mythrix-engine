# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Smoke tests for the actual Typer app wiring — just `--help` on every
command, which exercises real Typer argument parsing without needing a running
Kùzu/Chroma/Ollama."""

from typer.testing import CliRunner

from mythrix.cli.main import app

runner = CliRunner()


def test_root_help_lists_ingestion_and_preview_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "load-signs" in result.output
    assert "load-documents" in result.output
    assert "preview-segments" in result.output


def test_no_query_command_is_registered() -> None:
    """Querying is served by `/api/query` over the region shape (ADR-013) —
    the CLI is an ingestion surface only (FR-10)."""
    assert "query" not in runner.invoke(app, ["--help"]).output
    assert runner.invoke(app, ["query", "--help"]).exit_code != 0


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


def test_preview_segments_help_lists_expected_options() -> None:
    result = runner.invoke(app, ["preview-segments", "--help"])

    assert result.exit_code == 0
    assert "--json" in result.output
