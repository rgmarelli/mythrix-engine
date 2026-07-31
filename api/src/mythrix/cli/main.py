# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""`mythrix` CLI entrypoint — registers the ingestion commands (`load-signs`,
`load-documents`) and `preview-segments`, a store-free segmentation preview.
Querying is served by `/api/query`."""

from __future__ import annotations

import typer

from mythrix.cli.commands.load_documents import load_documents
from mythrix.cli.commands.load_signs import load_signs
from mythrix.cli.commands.preview_segments import preview_segments

app = typer.Typer(name="mythrix", help="Explainable symbolic-interpretation engine.")
app.command(name="load-signs")(load_signs)
app.command(name="load-documents")(load_documents)
app.command(name="preview-segments")(preview_segments)


if __name__ == "__main__":
    app()
