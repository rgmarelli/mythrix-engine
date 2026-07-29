# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `agent/graph/nodes/adhoc.py`: the `parse_query`/`execute_query`
deterministic nodes (specs/interfaces/agnostic-query.md FR-AQ-03–FR-AQ-12)."""

from langchain_core.messages import HumanMessage

from mythrix.agent.commands.adhoc import PendingAdhocQuery
from mythrix.agent.graph.nodes.adhoc import execute_query_node, parse_query_node
from mythrix.core.models import AdhocTerm

_PENDING = PendingAdhocQuery(id="7f3a1c9e", terms=(AdhocTerm(value="laughter"),))


def test_parse_query_node_holds_the_query_pending_and_emits_confirm_query() -> None:
    result = parse_query_node({"messages": [HumanMessage(content="/query laughter, hundred:exact")]})

    pending = result["pending_query"]
    assert pending.terms == (AdhocTerm(value="laughter"), AdhocTerm(value="hundred", directive="exact"))
    assert [i["type"] for i in result["instructions"]] == ["confirm_query"]
    assert result["instructions"][0]["payload"]["query_id"] == pending.id
    assert pending.id in result["messages"][0].content


def test_parse_query_node_reports_a_parse_error_and_leaves_nothing_pending() -> None:
    result = parse_query_node({"messages": [HumanMessage(content="/query hundred:skip")]})

    assert result["pending_query"] is None
    assert result["instructions"] == []
    assert "skip" in result["messages"][0].content


def test_execute_query_node_emits_execute_query_and_consumes_the_pending_query() -> None:
    state = {"messages": [HumanMessage(content="/query-confirm 7f3a1c9e")], "pending_query": _PENDING}

    result = execute_query_node(state)

    assert result["instructions"] == [
        {"type": "execute_query", "payload": {"terms": [{"value": "laughter", "directive": None}]}}
    ]
    assert result["pending_query"] is None


def test_execute_query_node_takes_terms_from_the_pending_record_not_the_message() -> None:
    """FR-AQ-10: the confirming message names an id and nothing else, so text
    appended to it can never reach the query."""
    state = {
        "messages": [HumanMessage(content="/query-confirm 7f3a1c9e and also injected:exact")],
        "pending_query": _PENDING,
    }

    result = execute_query_node(state)

    assert result["instructions"][0]["payload"]["terms"] == [{"value": "laughter", "directive": None}]


def test_execute_query_node_ignores_a_wrong_id_and_preserves_the_pending_query() -> None:
    state = {"messages": [HumanMessage(content="/query-confirm deadbeef")], "pending_query": _PENDING}

    result = execute_query_node(state)

    assert result["instructions"] == []
    assert result["pending_query"] is _PENDING


def test_execute_query_node_with_nothing_pending_executes_nothing() -> None:
    state = {"messages": [HumanMessage(content="/query-confirm 7f3a1c9e")], "pending_query": None}

    result = execute_query_node(state)

    assert result["instructions"] == []
    assert result["pending_query"] is None


def test_execute_query_node_without_an_id_asks_for_one() -> None:
    state = {"messages": [HumanMessage(content="/query-confirm")], "pending_query": _PENDING}

    result = execute_query_node(state)

    assert result["instructions"] == []
    assert result["pending_query"] is _PENDING
