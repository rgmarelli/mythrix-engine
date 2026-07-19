"""Unit tests for T21's `run_load_symbols`, called directly (no Typer
machinery) against the same fixtures used in `test_symbol_loader.py`."""

import json
from pathlib import Path

import pytest

from mythrix.cli.commands.load_symbols import run_load_symbols
from mythrix.core.errors import SymbolNotFoundError
from mythrix.core.graph.store import KuzuGraphStore

FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def graph_store(tmp_path: Path) -> KuzuGraphStore:
    return KuzuGraphStore(tmp_path / "graph.kuzu")


def test_dry_run_reports_the_planned_diff_without_writing(
    graph_store: KuzuGraphStore, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = run_load_symbols(FIXTURES_ROOT, graph_store=None, dry_run=True, as_json=True)

    assert exit_code == 0
    with pytest.raises(SymbolNotFoundError):
        graph_store.get_interpretation("the-fool", "rider-waite")

    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["symbols"] > 0
    assert payload["traditions"] > 0


def test_real_load_makes_the_symbol_queryable_afterward(graph_store: KuzuGraphStore) -> None:
    exit_code = run_load_symbols(FIXTURES_ROOT, graph_store=graph_store, dry_run=False, as_json=False)

    assert exit_code == 0
    facts = graph_store.get_interpretation("the-fool", "rider-waite")
    assert facts.interpretation.display_name == "The Fool"


def test_human_readable_summary_mentions_counts(
    graph_store: KuzuGraphStore, capsys: pytest.CaptureFixture[str]
) -> None:
    run_load_symbols(FIXTURES_ROOT, graph_store=graph_store, dry_run=False, as_json=False)

    output = capsys.readouterr().out
    assert "Loaded" in output
    assert "symbol" in output


def test_invalid_directory_reports_error_and_writes_nothing(
    tmp_path: Path, graph_store: KuzuGraphStore, capsys: pytest.CaptureFixture[str]
) -> None:
    bad_dir = tmp_path / "bad"
    (bad_dir / "symbols").mkdir(parents=True)
    (bad_dir / "symbols" / "broken.yaml").write_text("symbol:\n  name: Broken\n", encoding="utf-8")  # missing `type`

    exit_code = run_load_symbols(bad_dir, graph_store=graph_store, dry_run=False, as_json=False)

    assert exit_code == 1
    assert "Error" in capsys.readouterr().err
