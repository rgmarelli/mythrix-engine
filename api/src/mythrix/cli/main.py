"""`mythrix` CLI entrypoint — registers the three commands: `query`,
`load-signs`, `load-documents`."""

from __future__ import annotations

import typer

from mythrix.cli.commands.load_documents import load_documents
from mythrix.cli.commands.load_signs import load_signs
from mythrix.cli.commands.query import query

app = typer.Typer(name="mythrix", help="Explainable symbolic-interpretation engine.")
app.command(name="query")(query)
app.command(name="load-signs")(load_signs)
app.command(name="load-documents")(load_documents)


if __name__ == "__main__":
    app()
