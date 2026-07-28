"""Deterministic handling of the `/query` and `/query-confirm` chat commands
(specs/interfaces/agnostic-query.md FR-AQ-01–FR-AQ-14): term parsing,
confirmation rendering, and instruction building — no generation model is
involved at any point, so the confirmation gate is a property of this code
rather than of model compliance (ADR-010).

Pure functions and dataclasses only. `agent/graph.py` wires these into nodes;
nothing here imports LangGraph, so the parsing and rendering rules are
testable on their own."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from mythrix.core.errors import AdhocQueryValidationError
from mythrix.core.models import AdhocTerm

QUERY_COMMAND = "/query"
CONFIRM_COMMAND = "/query-confirm"

_DIRECTIVES = ("exact", "filter")
_SYNTAX_HELP = "Syntax: /query term, another term, term:exact, term:filter"


@dataclass(frozen=True)
class PendingAdhocQuery:
    """A parsed term list awaiting confirmation, held in session state under
    a backend-generated id (FR-AQ-04). Nothing has been retrieved for it."""

    id: str
    terms: tuple[AdhocTerm, ...]


def command_of(message: str) -> str | None:
    """The ad-hoc command `message` invokes, or `None` for an ordinary
    message. Matches the whole head token rather than a prefix — a
    `startswith` test would read `/query-confirm` as `/query`."""
    head = message.strip().partition(" ")[0].lower()
    return head if head in (QUERY_COMMAND, CONFIRM_COMMAND) else None


def is_adhoc_command(message: str) -> bool:
    return command_of(message) is not None


def _argument_of(message: str) -> str:
    return message.strip().partition(" ")[2].strip()


def parse_query_command(message: str) -> tuple[AdhocTerm, ...]:
    """Parses a `/query` command's comma-separated terms, each optionally
    carrying one `:exact`/`:filter` directive suffix (FR-AQ-02). Raises
    `AdhocQueryValidationError` naming the accepted syntax when the command
    supplies no terms, a directive outside the vocabulary, or a directive
    with no value (FR-AQ-03). A term containing a literal `:` is rejected
    rather than silently mis-parsed."""
    terms: list[AdhocTerm] = []
    for item in (raw.strip() for raw in _argument_of(message).split(",")):
        if not item:
            continue
        value, separator, suffix = item.rpartition(":")
        if not separator:
            terms.append(AdhocTerm(value=item))
            continue
        if suffix not in _DIRECTIVES:
            raise AdhocQueryValidationError(f"unknown directive {':' + suffix!r}. {_SYNTAX_HELP}")
        value = value.strip()
        if not value:
            raise AdhocQueryValidationError(f"directive {':' + suffix!r} names no term. {_SYNTAX_HELP}")
        terms.append(AdhocTerm(value=value, directive=suffix))  # type: ignore[arg-type]
    if not terms:
        raise AdhocQueryValidationError(f"no terms given. {_SYNTAX_HELP}")
    return tuple(terms)


def confirm_id_of(message: str) -> str:
    """The pending-query id a `/query-confirm` command names, or `""`."""
    return _argument_of(message).partition(" ")[0]


def new_query_id() -> str:
    return uuid4().hex[:8]


def confirm_command_for(query_id: str) -> str:
    return f"{CONFIRM_COMMAND} {query_id}"


def _render_terms(terms: tuple[AdhocTerm, ...]) -> str:
    return "\n".join(f"- {term.value}" + (f" [{term.directive}]" if term.directive else "") for term in terms)


def render_confirmation(terms: tuple[AdhocTerm, ...], query_id: str) -> str:
    """The reply restating a parsed query and naming the command that runs it
    (FR-AQ-06) — spelled out so the flow is completable without a consumer
    that interprets instructions."""
    return f"Parsed query:\n{_render_terms(terms)}\n\nSend `{confirm_command_for(query_id)}` to run it."


def render_dispatch(terms: tuple[AdhocTerm, ...]) -> str:
    return f"Confirmed — query dispatched:\n{_render_terms(terms)}"


def _terms_payload(terms: tuple[AdhocTerm, ...]) -> list[dict]:
    return [term.model_dump() for term in terms]


def confirm_query_instruction(query_id: str, terms: tuple[AdhocTerm, ...]) -> dict:
    """Carries `confirm_command` verbatim so a consumer's affordance sends the
    identical string a human would type (FR-AQ-07)."""
    return {
        "type": "confirm_query",
        "payload": {
            "query_id": query_id,
            "terms": _terms_payload(terms),
            "confirm_command": confirm_command_for(query_id),
        },
    }


def execute_query_instruction(terms: tuple[AdhocTerm, ...]) -> dict:
    """Transport-agnostic by design: no method, no path (FR-AQ-14)."""
    return {"type": "execute_query", "payload": {"terms": _terms_payload(terms)}}
