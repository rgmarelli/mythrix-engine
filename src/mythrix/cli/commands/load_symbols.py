"""`mythrix load-symbols`: wraps `symbol_loader` (FR4, FR5).

`--dry-run` calls `build_plan()` only — the same validation pass `load_directory`
runs internally, just without the write phase — so "nothing is written" is
structural, not a separate code path that could drift from the real one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from mythrix.core.config import Settings
from mythrix.core.errors import IngestValidationError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.loaders.symbol_loader import LoadPlan, build_plan, load_directory


def _summarize(plan: LoadPlan) -> dict[str, int]:
    return {
        "traditions": len(plan.traditions),
        "sources": len(plan.sources),
        "symbols": len(plan.bare_symbols),
        "interpretations": len(plan.interpretations),
        "relationships": len(plan.relationships),
    }


def run_load_symbols(path: Path, *, graph_store: KuzuGraphStore | None, dry_run: bool, as_json: bool) -> int:
    """`graph_store=None` is only valid together with `dry_run=True` — a real
    load needs somewhere to write to."""
    try:
        plan = build_plan(path) if dry_run else load_directory(path, graph_store)
    except IngestValidationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        return 1

    summary = _summarize(plan)
    if as_json:
        typer.echo(json.dumps({"dry_run": dry_run, **summary}, indent=2))
    else:
        verb = "Would load" if dry_run else "Loaded"
        typer.echo(
            f"{verb}: {summary['traditions']} tradition(s), {summary['sources']} source(s), "
            f"{summary['symbols']} symbol(s) ({summary['interpretations']} interpretation(s)), "
            f"{summary['relationships']} relationship(s)."
        )
    return 0


def load_symbols(
    path: Annotated[Path, typer.Argument(help="Directory containing traditions/sources/symbols YAML")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate and report without writing")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    graph_store = None if dry_run else KuzuGraphStore(Settings().kuzu_db_path)
    exit_code = run_load_symbols(path, graph_store=graph_store, dry_run=dry_run, as_json=as_json)
    raise typer.Exit(code=exit_code)
