"""Package exposing deterministic agent slash-commands (`/query`,
`/query-confirm`, `/summarize`, `/augment`, `/augment-confirm`). Pure
parsing/detection only — no LangGraph import anywhere under this package."""

from __future__ import annotations

from mythrix.agent.commands import adhoc, augment, summarize

__all__ = ["adhoc", "augment", "summarize", "resolve_command"]

_HANDLERS = (
    adhoc.command_of,
    summarize.command_of,
    augment.command_of,
)


def resolve_command(message: str) -> str | None:
    """The command `message` invokes, or `None` for an ordinary message —
    the union of every registered command module's own `command_of`."""
    for handler in _HANDLERS:
        if cmd := handler(message):
            return cmd
    return None
