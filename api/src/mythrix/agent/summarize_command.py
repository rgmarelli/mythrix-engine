"""Deterministic handling of the `/summarize` chat command
(specs/interfaces/agent.md FR-AG-33–FR-AG-36): command detection, focus/concept
resolution, and hotspot-coordinate parsing — no generation model or LangGraph
import here, so this is testable on its own (ADR-012). `agent/graph.py` wires
these into `summarize_node`."""

from __future__ import annotations

from mythrix.core.retrieval.pipeline import parse_region_id

SUMMARIZE_COMMAND = "/summarize"

NO_HOTSPOT_MESSAGE = "No passage is currently selected — select a hotspot first, then send /summarize again."


def command_of(message: str) -> str | None:
    """`SUMMARIZE_COMMAND` if `message` invokes it, else `None` — same
    contract as `adhoc_query.py::command_of`, so `route_input` dispatches on
    all three commands the same way. Matches the whole head token, not a
    prefix — `/summarized` must not match."""
    head = message.strip().partition(" ")[0].lower()
    return SUMMARIZE_COMMAND if head == SUMMARIZE_COMMAND else None


def focus_of(message: str) -> str:
    """The free-text focus following `/summarize`, if any."""
    return message.strip().partition(" ")[2].strip()


def concepts_for(focus: str, interpretant: str | None) -> list[str]:
    """The `summarize_passage` tool's `concepts` argument (FR-AG-35): the
    command's own trailing focus text wins; absent that, the session's
    currently selected interpretant; absent both, no scoping concept."""
    if focus:
        return [focus]
    if interpretant:
        return [interpretant]
    return []


def resolve_hotspot(region_id: str) -> tuple[str, int, int]:
    """The active hotspot's `(source_id, start_ordinal, end_ordinal)`,
    parsed from its `region_id` — everything `fetch_segments` needs to
    retrieve the passage verbatim. Raises `ValueError` on a malformed
    `region_id` (see `parse_region_id`)."""
    return parse_region_id(region_id)
