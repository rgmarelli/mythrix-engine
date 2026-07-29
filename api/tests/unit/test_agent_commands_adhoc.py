# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `agent/commands/adhoc.py`: the deterministic `/query` and
`/query-confirm` parsing, rendering, and instruction building
(specs/interfaces/agnostic-query.md FR-AQ-02, FR-AQ-03, FR-AQ-06, FR-AQ-07,
FR-AQ-14). Pure functions — nothing here touches a store, a graph, or a model."""

import pytest

from mythrix.agent.commands.adhoc import (
    CONFIRM_COMMAND,
    QUERY_COMMAND,
    command_of,
    confirm_id_of,
    confirm_query_instruction,
    execute_query_instruction,
    is_adhoc_command,
    new_query_id,
    parse_query_command,
    render_confirmation,
)
from mythrix.core.errors import AdhocQueryValidationError
from mythrix.core.models import AdhocTerm


def test_command_of_distinguishes_query_from_query_confirm() -> None:
    """A `startswith` test would read `/query-confirm` as `/query`, silently
    routing every confirmation into the parser."""
    assert command_of("/query laughter") == QUERY_COMMAND
    assert command_of("/query-confirm 7f3a1c9e") == CONFIRM_COMMAND


def test_command_of_ignores_ordinary_messages_and_lookalikes() -> None:
    assert command_of("what does the tower mean?") is None
    assert command_of("/queryish laughter") is None
    assert command_of("/summarize") is None
    assert is_adhoc_command("/QUERY laughter") is True


def test_parse_query_command_reads_plain_and_directive_terms() -> None:
    terms = parse_query_command("/query laughter, child, hundred:exact, pisces:filter")
    assert terms == (
        AdhocTerm(value="laughter"),
        AdhocTerm(value="child"),
        AdhocTerm(value="hundred", directive="exact"),
        AdhocTerm(value="pisces", directive="filter"),
    )


def test_parse_query_command_tolerates_whitespace_and_empty_items() -> None:
    terms = parse_query_command("/query   laughter ,, sacred fire :exact ,  ")
    assert terms == (AdhocTerm(value="laughter"), AdhocTerm(value="sacred fire", directive="exact"))


def test_parse_query_command_without_terms_raises() -> None:
    with pytest.raises(AdhocQueryValidationError):
        parse_query_command("/query")
    with pytest.raises(AdhocQueryValidationError):
        parse_query_command("/query   , ,")


def test_parse_query_command_unknown_directive_raises() -> None:
    with pytest.raises(AdhocQueryValidationError, match="skip"):
        parse_query_command("/query laughter, hundred:skip")


def test_parse_query_command_directive_without_a_term_raises() -> None:
    with pytest.raises(AdhocQueryValidationError):
        parse_query_command("/query :exact")


def test_parse_query_command_error_names_the_accepted_syntax() -> None:
    with pytest.raises(AdhocQueryValidationError, match=r"/query term"):
        parse_query_command("/query")


def test_confirm_id_of_reads_the_id_or_returns_empty() -> None:
    assert confirm_id_of("/query-confirm 7f3a1c9e") == "7f3a1c9e"
    assert confirm_id_of("/query-confirm") == ""


def test_new_query_id_is_short_enough_to_retype() -> None:
    """FR-AQ-06 depends on a human being able to type the confirm command
    straight out of the reply text."""
    assert len(new_query_id()) == 8
    assert new_query_id() != new_query_id()


def test_render_confirmation_lists_terms_and_names_the_confirm_command() -> None:
    terms = (AdhocTerm(value="laughter"), AdhocTerm(value="hundred", directive="exact"))
    text = render_confirmation(terms, "7f3a1c9e")
    assert "- laughter" in text
    assert "- hundred [exact]" in text
    assert "/query-confirm 7f3a1c9e" in text


def test_confirm_query_instruction_carries_the_command_verbatim() -> None:
    terms = (AdhocTerm(value="laughter"),)
    instruction = confirm_query_instruction("7f3a1c9e", terms)
    assert instruction == {
        "type": "confirm_query",
        "payload": {
            "query_id": "7f3a1c9e",
            "terms": [{"value": "laughter", "directive": None}],
            "confirm_command": "/query-confirm 7f3a1c9e",
        },
    }


def test_execute_query_instruction_carries_no_transport_detail() -> None:
    instruction = execute_query_instruction((AdhocTerm(value="hundred", directive="exact"),))
    assert instruction == {"type": "execute_query", "payload": {"terms": [{"value": "hundred", "directive": "exact"}]}}
    assert "method" not in instruction and "path" not in instruction
