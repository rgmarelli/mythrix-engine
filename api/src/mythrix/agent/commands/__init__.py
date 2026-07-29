"""Package exposing deterministic agent slash-commands (`/query`,
`/query-confirm`, `/summarize`, `/augment`, `/augment-confirm`). Pure
parsing/detection only — no LangGraph import anywhere under this package."""

from __future__ import annotations

from dataclasses import dataclass

from mythrix.agent.commands import adhoc, augment, summarize
from mythrix.agent.commands.adhoc import PendingAdhocQuery
from mythrix.agent.commands.augment import PendingAugmentation

__all__ = ["adhoc", "augment", "summarize", "resolve_command", "PendingCommands"]

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


@dataclass(frozen=True)
class PendingCommands:
    """The turn's outstanding command confirmations, one slot per command
    that supports one (agnostic-query.md FR-AQ-05, augmentation.md FR-AU-08)
    — bundled so a caller carrying this across a turn boundary needn't know
    how many such commands exist."""

    query: PendingAdhocQuery | None = None
    augmentation: PendingAugmentation | None = None
