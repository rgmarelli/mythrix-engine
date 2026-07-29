"""Deterministic handling of the `/discover` and `/discover-confirm` chat
commands (specs/interfaces/discovery.md FR-DS-01–FR-DS-08, FR-DS-20): parsing
the command's two inputs, confirmation rendering, and report composition — no
generation model is involved at any point here, so the confirmation gate is a
property of this code rather than of model compliance (ADR-010, ADR-015).

Pure functions and dataclasses only. `agent/graph/nodes/discover.py` wires
these into nodes; nothing here imports LangGraph, so the parsing and rendering
rules are testable on their own."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from mythrix.agent.commands.adhoc import parse_terms, render_terms
from mythrix.core.errors import AdhocQueryValidationError
from mythrix.core.models import AdhocTerm

DISCOVER_COMMAND = "/discover"
DISCOVER_CONFIRM_COMMAND = "/discover-confirm"

_QUOTE = '"'
_SYNTAX_HELP = 'Syntax: /discover "what to look for", term, another term, term:exact, term:filter'

NO_MATCH_MESSAGE = "Nothing in the corpus matched those terms above the match floor."
NO_PASSAGE_MESSAGE = "None of the matched regions could be read back from the corpus."


@dataclass(frozen=True)
class PendingDiscovery:
    """A parsed discovery awaiting confirmation, held in session state under a
    backend-generated id (FR-DS-05). Nothing has been retrieved for it.

    `focus` and `terms` stay separate all the way through: only `terms` ever
    becomes query text (FR-DS-04)."""

    id: str
    focus: str
    terms: tuple[AdhocTerm, ...]


@dataclass(frozen=True)
class RegionFinding:
    """One analyzed region's reading, with the region identity the report
    labels it by. `label` is the citation marker the consolidation cites
    (FR-DS-21); `text` is the generated finding, already marker-stripped."""

    label: str
    source: str
    locator: str
    rank: int
    score: float
    text: str


def command_of(message: str) -> str | None:
    """The discovery command `message` invokes, or `None`. Matches the whole
    head token rather than a prefix — a `startswith` test would read
    `/discover-confirm` as `/discover`."""
    head = message.strip().partition(" ")[0].lower()
    return head if head in (DISCOVER_COMMAND, DISCOVER_CONFIRM_COMMAND) else None


def _argument_of(message: str) -> str:
    return message.strip().partition(" ")[2].strip()


def parse_discover_command(message: str) -> tuple[str, tuple[AdhocTerm, ...]]:
    """The `(focus, terms)` a `/discover` command supplies (FR-DS-01).

    The focus is delimited by double quotes, so it may contain the commas,
    colons and directive suffixes that would otherwise parse as terms
    (FR-DS-03). Everything after the closing quote is the term list, parsed by
    the same rules `/query` uses. Raises `AdhocQueryValidationError` naming the
    accepted syntax when the focus is absent, unterminated or empty, or when
    no terms follow it (FR-DS-02)."""
    argument = _argument_of(message)
    if not argument.startswith(_QUOTE):
        raise AdhocQueryValidationError(f"the analysis focus must come first, in double quotes. {_SYNTAX_HELP}")
    focus, closing, remainder = argument[1:].partition(_QUOTE)
    if not closing:
        raise AdhocQueryValidationError(f"the analysis focus is missing its closing quote. {_SYNTAX_HELP}")
    focus = focus.strip()
    if not focus:
        raise AdhocQueryValidationError(f"the analysis focus is empty. {_SYNTAX_HELP}")
    return focus, parse_terms(remainder.strip().removeprefix(","), syntax_help=_SYNTAX_HELP)


def confirm_id_of(message: str) -> str:
    """The pending-discovery id a `/discover-confirm` command names, or `""`."""
    return _argument_of(message).partition(" ")[0]


def new_discovery_id() -> str:
    return uuid4().hex[:8]


def confirm_command_for(discovery_id: str) -> str:
    return f"{DISCOVER_CONFIRM_COMMAND} {discovery_id}"


def region_label(rank: int) -> str:
    """The citation marker for the region at 1-based retrieval `rank`
    (FR-DS-21). Numbering follows retrieval's own order, so a region that
    could not be read leaves a gap rather than shifting its successors."""
    return f"[R{rank}]"


def render_plan(focus: str, terms: tuple[AdhocTerm, ...], max_regions: int, discovery_id: str) -> str:
    """The reply restating a parsed discovery and naming the command that runs
    it (FR-DS-05). States the analysis bound, not how many regions the query
    would match — the plan turn retrieves nothing (FR-DS-06)."""
    return (
        f"Parsed discovery:\n\n"
        f"Focus: {focus}\n\n"
        f"Terms:\n{render_terms(terms)}\n\n"
        f"A run reads up to {max_regions} of the highest-ranked matching regions, "
        f"one generation call each, plus one to consolidate them.\n\n"
        f"Send `{confirm_command_for(discovery_id)}` to run it."
    )


def confirm_discovery_instruction(discovery_id: str, focus: str, terms: tuple[AdhocTerm, ...]) -> dict:
    """Carries `confirm_command` verbatim so a consumer's affordance sends the
    identical string a human would type (FR-DS-31, cf. FR-AQ-07). Declared with
    no binding: it triggers no request, so a consumer handles it in-app."""
    return {
        "type": "confirm_discovery",
        "payload": {
            "discovery_id": discovery_id,
            "focus": focus,
            "terms": [term.model_dump() for term in terms],
            "confirm_command": confirm_command_for(discovery_id),
        },
    }


def render_report(focus: str, matched_count: int, findings: tuple[RegionFinding, ...], consolidation: str) -> str:
    """The run's complete reply (FR-DS-20): the consolidation first, then one
    labeled section per analyzed region. Composed here rather than generated,
    so every region's identity, locator, rank and score are the retrieved
    values verbatim."""
    scope = f"Read {len(findings)} of {matched_count} matching region(s)."
    sections = "\n\n".join(
        f"### {finding.label} {finding.source} — {finding.locator}\n"
        f"rank {finding.rank} · score {finding.score:.3f}\n\n"
        f"{finding.text}"
        for finding in findings
    )
    return f"**{focus}**\n\n{consolidation}\n\n---\n\n{scope}\n\n{sections}"
