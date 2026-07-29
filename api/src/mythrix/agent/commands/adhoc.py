# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Deterministic handling of the `/query` and `/query-confirm` chat commands
(specs/interfaces/agnostic-query.md FR-AQ-01–FR-AQ-14): term parsing,
confirmation rendering, and instruction building — no generation model is
involved at any point, so the confirmation gate is a property of this code
rather than of model compliance (ADR-010).

Pure functions and dataclasses only. `agent/graph/nodes/adhoc.py` wires these
into nodes; nothing here imports LangGraph, so the parsing and rendering
rules are testable on their own."""

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


def parse_terms(text: str, *, syntax_help: str = _SYNTAX_HELP) -> tuple[AdhocTerm, ...]:
    """Parses a comma-separated term list, each term optionally carrying one
    `:exact`/`:filter` directive suffix (FR-AQ-02). Raises
    `AdhocQueryValidationError` naming the accepted syntax when the list
    supplies no terms, a directive outside the vocabulary, or a directive with
    no value (FR-AQ-03). A term containing a literal `:` is rejected rather
    than silently mis-parsed.

    The directive vocabulary lives here alone: every command taking a term
    list calls this, so the two cannot fork. `syntax_help` lets a caller name
    its own command in the rejection while the rules stay shared."""
    terms: list[AdhocTerm] = []
    for item in (raw.strip() for raw in text.split(",")):
        if not item:
            continue
        value, separator, suffix = item.rpartition(":")
        if not separator:
            terms.append(AdhocTerm(value=item))
            continue
        if suffix not in _DIRECTIVES:
            raise AdhocQueryValidationError(f"unknown directive {':' + suffix!r}. {syntax_help}")
        value = value.strip()
        if not value:
            raise AdhocQueryValidationError(f"directive {':' + suffix!r} names no term. {syntax_help}")
        terms.append(AdhocTerm(value=value, directive=suffix))  # type: ignore[arg-type]
    if not terms:
        raise AdhocQueryValidationError(f"no terms given. {syntax_help}")
    return tuple(terms)


def parse_query_command(message: str) -> tuple[AdhocTerm, ...]:
    """The terms a `/query` command supplies (FR-AQ-02, FR-AQ-03)."""
    return parse_terms(_argument_of(message))


def confirm_id_of(message: str) -> str:
    """The pending-query id a `/query-confirm` command names, or `""`."""
    return _argument_of(message).partition(" ")[0]


def new_query_id() -> str:
    return uuid4().hex[:8]


def confirm_command_for(query_id: str) -> str:
    return f"{CONFIRM_COMMAND} {query_id}"


def render_terms(terms: tuple[AdhocTerm, ...]) -> str:
    """One parsed term per line, with its directive — shared by every command
    that restates a term list back to the user."""
    return "\n".join(f"- {term.value}" + (f" [{term.directive}]" if term.directive else "") for term in terms)


def render_confirmation(terms: tuple[AdhocTerm, ...], query_id: str) -> str:
    """The reply restating a parsed query and naming the command that runs it
    (FR-AQ-06) — spelled out so the flow is completable without a consumer
    that interprets instructions."""
    return f"Parsed query:\n{render_terms(terms)}\n\nSend `{confirm_command_for(query_id)}` to run it."


def render_dispatch(terms: tuple[AdhocTerm, ...]) -> str:
    return f"Confirmed — query dispatched:\n{render_terms(terms)}"


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
