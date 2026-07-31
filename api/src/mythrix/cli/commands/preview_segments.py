# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""`mythrix preview-segments`: lists every segment's own locator a corpus
source's declared segmentation produces, straight from its `.txt`
(FR-CO-14).

Unlike `load-documents --dry-run`, this never opens the graph or vector
store — no `Settings`, no `KuzuGraphStore`/`ChromaVectorStore` handle at all
— so it works even while another process (a running API server) already
holds Kùzu's single-writer lock, and it's the fastest way to eyeball a
`chapter_section` source's actual locator text (e.g. does a subsection-level
segment still name its chapter?) before committing to a real, costly
reingest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from mythrix.core.errors import MythrixError
from mythrix.core.loaders.document_loader import preview_corpus_segments


def run_preview_segments(path: Path, *, as_json: bool) -> int:
    try:
        results = preview_corpus_segments(path)
    except MythrixError as exc:
        typer.echo(f"Error: {exc}", err=True)
        return 1

    if as_json:
        typer.echo(json.dumps({"results": results}, indent=2))
    elif not results:
        typer.echo("No corpus sources found.")
    else:
        for result in results:
            segments = result["segments"]
            unit = "segment" if len(segments) == 1 else "segments"
            typer.echo(f"{result['source_id']!r}: {len(segments)} {unit}")
            for segment in segments:
                typer.echo(f"  [{segment['ordinal']}] {segment['locator']}")
    return 0


def preview_segments(
    path: Annotated[Path, typer.Argument(help="Directory containing corpus <name>.yaml/<name>.txt pairs")],
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    exit_code = run_preview_segments(path, as_json=as_json)
    raise typer.Exit(code=exit_code)
