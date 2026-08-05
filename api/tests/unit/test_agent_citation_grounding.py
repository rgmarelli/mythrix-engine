# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `agent/citation_grounding.py` — reading a citable tool
result's own opaque `grounding_id`s (ADR-022) off `get_sign`/`query_sign`/
`fetch_segments` payloads, the listing-tools-only skip, and the fuller
`Evidence` (source/locator/text) the fact-checker needs (ADR-025)."""

import json

from langchain_core.messages import ToolMessage

from mythrix.agent.citation_grounding import (
    Evidence,
    evidence_from_get_sign_payload,
    evidence_from_query_sign_payload,
    evidence_from_segments_payload,
    evidence_from_tool_messages,
    grounding_ids,
    only_listing_tools_called,
)


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


def test_evidence_from_get_sign_payload_shares_denotation_across_citations() -> None:
    """A `get_sign` citation carries no text of its own — every citation for
    one call backs the same manifestation facts, so each shares the same
    evidence text (ADR-025)."""
    payload = {
        "denotation": "Joy, vitality, and the clarity of illuminated truth.",
        "interpretants": [{"type": "concept", "value": "joy"}],
        "citations": [
            {"source": "Waite", "locator": "p. 143", "grounding_id": "G111111"},
            {"source": "Case", "locator": "p. 88", "grounding_id": "G222222"},
        ],
    }

    evidence = evidence_from_get_sign_payload(payload)

    assert evidence == [
        Evidence(
            grounding_id="G111111",
            source="Waite",
            locator="p. 143",
            text="Joy, vitality, and the clarity of illuminated truth. Interpretants: joy.",
        ),
        Evidence(
            grounding_id="G222222",
            source="Case",
            locator="p. 88",
            text="Joy, vitality, and the clarity of illuminated truth. Interpretants: joy.",
        ),
    ]


def test_evidence_from_get_sign_payload_empty_on_error() -> None:
    assert evidence_from_get_sign_payload({"error": "unknown sign 'sun'"}) == []


def test_evidence_from_query_sign_payload_reads_each_segments_own_text() -> None:
    payload = {
        "regions": [
            {
                "source": "Genesis",
                "segments": [
                    {"locator": "Genesis 1:3", "text": "Let there be light.", "grounding_id": "S111111"},
                    {"locator": "Genesis 1:4", "text": "And God saw the light.", "grounding_id": "S222222"},
                ],
            }
        ]
    }

    evidence = evidence_from_query_sign_payload(payload)

    assert evidence == [
        Evidence(grounding_id="S111111", source="Genesis", locator="Genesis 1:3", text="Let there be light."),
        Evidence(grounding_id="S222222", source="Genesis", locator="Genesis 1:4", text="And God saw the light."),
    ]


def test_evidence_from_query_sign_payload_empty_on_error() -> None:
    assert evidence_from_query_sign_payload({"error": "unknown sign 'sun'"}) == []


def test_evidence_from_segments_payload_falls_back_to_section_for_source() -> None:
    """`fetch_segments` carries no parent source title of its own — `section`
    stands in for it."""
    payload = [
        {"locator": "Genesis 1:3", "section": "Genesis", "text": "Let there be light.", "grounding_id": "S111111"},
        {"locator": "Genesis 1:4", "section": None, "text": "And God saw the light.", "grounding_id": "S222222"},
    ]

    evidence = evidence_from_segments_payload(payload)

    assert evidence == [
        Evidence(grounding_id="S111111", source="Genesis", locator="Genesis 1:3", text="Let there be light."),
        Evidence(grounding_id="S222222", source="Genesis 1:4", locator="Genesis 1:4", text="And God saw the light."),
    ]


def test_evidence_from_segments_payload_skips_errors() -> None:
    assert evidence_from_segments_payload([{"error": "unknown source"}]) == []


def test_evidence_from_tool_messages_dispatches_by_tool_name() -> None:
    get_sign_message = _tool_message(
        "get_sign",
        {
            "denotation": "Joy.",
            "interpretants": [],
            "citations": [{"source": "Waite", "locator": "p. 1", "grounding_id": "G111111"}],
        },
    )
    fetch_message = _tool_message(
        "fetch_segments",
        [{"locator": "Genesis 1:1", "section": "Genesis", "text": "In the beginning.", "grounding_id": "S222222"}],
    )
    listing_message = _tool_message("list_signs", [{"slug": "the-sun", "name": "The Sun"}])

    evidence = evidence_from_tool_messages([get_sign_message, fetch_message, listing_message])

    assert {e.grounding_id for e in evidence} == {"G111111", "S222222"}


def test_evidence_from_tool_messages_empty_for_no_evidence() -> None:
    assert evidence_from_tool_messages([]) == []
    assert evidence_from_tool_messages([_tool_message("list_signs", [])]) == []
