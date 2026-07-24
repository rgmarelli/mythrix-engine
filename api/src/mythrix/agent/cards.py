"""Structured cards for the chat thread (master spec.md FR-AG-19), built directly from the
tool results that grounded a turn — never parsed or inferred from the
model's free-text reply. Mirrors `AgentCard` (`api/routes.py`): every card
returned here is one of the two `type`s that shape defines, `"citation"` or
`"interpretant_chips"`."""

from __future__ import annotations


def _citation_card(*, source_label: str, locator: str, text: str) -> dict:
    return {"type": "citation", "source_label": source_label, "locator": locator, "text": text}


def _interpretant_chips_card(matches: list[dict]) -> dict:
    return {
        "type": "interpretant_chips",
        "chips": [
            {
                "interpretant": match["interpretant"],
                "kind": match["kind"],
                "score": match["score"],
                "segment_ordinal": match["segment_ordinal"],
            }
            for match in matches
        ],
    }


def _cards_for_query_sign(payload: dict) -> list[dict]:
    cards: list[dict] = []
    for region in payload.get("regions", ()):
        source_label = region.get("source", "")
        for segment in region.get("segments", ()):
            cards.append(
                _citation_card(
                    source_label=source_label, locator=segment.get("locator", ""), text=segment.get("text", "")
                )
            )
        if region.get("matches"):
            cards.append(_interpretant_chips_card(region["matches"]))
    return cards


def _cards_for_fetch_segments(payload: list) -> list[dict]:
    return [
        _citation_card(source_label="", locator=segment.get("locator", ""), text=segment.get("text", ""))
        for segment in payload
        if "error" not in segment
    ]


def _cards_for_get_sign(payload: dict) -> list[dict]:
    return [
        _citation_card(source_label=citation.get("source", ""), locator=citation.get("locator", ""), text="")
        for citation in payload.get("citations", ())
    ]


def build_cards(tool_name: str, payload: object) -> list[dict]:
    """`payload` is the tool result already parsed from JSON (see
    `turn_service.py`) — a `dict` for every tool except `fetch_segments`,
    which returns a `list`. A `{"error": ...}` payload (a caught
    `MythrixError`, `agent/tools.py`) produces no cards."""
    if tool_name == "query_sign" and isinstance(payload, dict) and "error" not in payload:
        return _cards_for_query_sign(payload)
    if tool_name == "fetch_segments" and isinstance(payload, list):
        return _cards_for_fetch_segments(payload)
    if tool_name == "get_sign" and isinstance(payload, dict) and "error" not in payload:
        return _cards_for_get_sign(payload)
    return []
