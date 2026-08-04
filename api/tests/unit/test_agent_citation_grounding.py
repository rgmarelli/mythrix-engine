# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `agent/citation_grounding.py` — reading a citable tool
result's own opaque `grounding_id`s (ADR-022) off `get_sign`/`query_sign`/
`fetch_segments` payloads, and the listing-tools-only skip."""

import json

from langchain_core.messages import ToolMessage

from mythrix.agent.citation_grounding import grounding_ids, only_listing_tools_called


def _tool_message(name: str, payload: object) -> ToolMessage:
    return ToolMessage(content=json.dumps(payload), name=name, tool_call_id="c")


def test_grounding_ids_reads_get_sign_citations() -> None:
    message = _tool_message("get_sign", {"citations": [{"source": "Waite", "grounding_id": "Gabc123"}]})
    assert grounding_ids([message]) == {"Gabc123"}


def test_grounding_ids_reads_query_sign_segments_across_regions() -> None:
    payload = {
        "regions": [
            {"segments": [{"grounding_id": "S111111"}, {"grounding_id": "S222222"}]},
            {"segments": [{"grounding_id": "S333333"}]},
        ]
    }
    message = _tool_message("query_sign", payload)
    assert grounding_ids([message]) == {"S111111", "S222222", "S333333"}


def test_grounding_ids_reads_fetch_segments_list() -> None:
    payload = [{"ordinal": 0, "grounding_id": "Saaaaaa"}, {"ordinal": 1, "grounding_id": "Sbbbbbb"}]
    message = _tool_message("fetch_segments", payload)
    assert grounding_ids([message]) == {"Saaaaaa", "Sbbbbbb"}


def test_grounding_ids_skips_error_payloads() -> None:
    get_sign_error = _tool_message("get_sign", {"error": "unknown sign 'sun'"})
    fetch_segments_error = _tool_message("fetch_segments", [{"error": "unknown source"}])
    assert grounding_ids([get_sign_error, fetch_segments_error]) == set()


def test_grounding_ids_ignores_unrelated_tool_names() -> None:
    message = _tool_message("list_signs", [{"slug": "the-sun", "name": "The Sun"}])
    assert grounding_ids([message]) == set()


def test_grounding_ids_combines_across_multiple_messages() -> None:
    first = _tool_message("get_sign", {"citations": [{"grounding_id": "G111111"}]})
    second = _tool_message("fetch_segments", [{"grounding_id": "S222222"}])
    assert grounding_ids([first, second]) == {"G111111", "S222222"}


def test_only_listing_tools_called_true_when_every_call_is_a_listing_tool() -> None:
    messages = [_tool_message("list_signs", []), _tool_message("list_traditions", [])]
    assert only_listing_tools_called(messages) is True


def test_only_listing_tools_called_false_when_any_call_is_not_a_listing_tool() -> None:
    messages = [_tool_message("list_signs", []), _tool_message("get_sign", {"citations": []})]
    assert only_listing_tools_called(messages) is False


def test_only_listing_tools_called_false_when_no_tools_were_called() -> None:
    assert only_listing_tools_called([]) is False
