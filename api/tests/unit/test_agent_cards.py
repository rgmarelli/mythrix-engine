"""Unit tests for `agent/cards.py::build_cards` — every card is built
directly from a tool result payload, one test per tool in the mapping."""

from mythrix.agent.cards import build_cards


def test_query_sign_builds_citation_and_interpretant_chip_cards() -> None:
    payload = {
        "regions": [
            {
                "region_id": "waite::0-1",
                "source": "The Pictorial Key to the Tarot",
                "matches": [
                    {"interpretant": "upheaval", "kind": "concept", "score": 0.9, "segment_ordinal": 0},
                ],
                "segments": [
                    {"ordinal": 0, "locator": "Ch. 1", "section": "", "text": "The tower falls."},
                ],
            }
        ]
    }

    cards = build_cards("query_sign", payload)

    assert cards == [
        {
            "type": "citation",
            "source_label": "The Pictorial Key to the Tarot",
            "locator": "Ch. 1",
            "text": "The tower falls.",
        },
        {
            "type": "interpretant_chips",
            "chips": [{"interpretant": "upheaval", "kind": "concept", "score": 0.9, "segment_ordinal": 0}],
        },
    ]


def test_query_sign_with_no_regions_returns_no_cards() -> None:
    assert build_cards("query_sign", {"regions": []}) == []


def test_query_sign_error_payload_returns_no_cards() -> None:
    assert build_cards("query_sign", {"error": "unknown sign"}) == []


def test_fetch_segments_builds_citation_cards() -> None:
    payload = [{"ordinal": 0, "locator": "1:1", "section": "Genesis", "text": "In the beginning."}]

    cards = build_cards("fetch_segments", payload)

    assert cards == [{"type": "citation", "source_label": "", "locator": "1:1", "text": "In the beginning."}]


def test_fetch_segments_skips_error_entries() -> None:
    assert build_cards("fetch_segments", [{"error": "no such source"}]) == []


def test_get_sign_builds_attribution_only_citation_cards() -> None:
    payload = {"sign": "The Tower", "citations": [{"source": "Waite", "locator": "p. 12"}]}

    cards = build_cards("get_sign", payload)

    assert cards == [{"type": "citation", "source_label": "Waite", "locator": "p. 12", "text": ""}]


def test_get_sign_needs_tradition_returns_no_cards() -> None:
    assert build_cards("get_sign", {"needs_tradition": True, "sign": "X", "traditions": []}) == []


def test_unrelated_tool_returns_no_cards() -> None:
    assert build_cards("list_signs", [{"slug": "the-tower"}]) == []
