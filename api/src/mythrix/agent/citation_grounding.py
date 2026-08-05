# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Reads a citable tool result's own opaque `grounding_id`s (ADR-022), and
the rest of the citable item alongside it (source/locator/text), off
`get_sign`/`query_sign`/`fetch_segments` payloads — the shared core
`turn_service.py`'s post-hoc check and the fact-check node
(`graph/nodes/fact_check.py`, ADR-025) both build on.

Two layers: `evidence_from_get_sign_payload`/`evidence_from_query_sign_payload`/
`evidence_from_segments_payload` read one tool's own payload dict/list
directly — the shape a deterministic node like `summarize_node` already
holds without any `ToolMessage` wrapping — and `evidence_from_tool_messages`
dispatches across a turn's `ToolMessage`s by tool name, for the
conversational graph path alone.

Kept separate from `agent/citations.py`, which is deliberately typeless
(works on text and a caller-supplied id set, never on tool payloads), and
from `turn_service.py`, a higher-level orchestrator that composes the graph
rather than something the graph should depend on — this module sits below
both.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from langchain_core.messages import ToolMessage

_LISTING_TOOL_NAMES = frozenset({"list_signs", "list_traditions", "list_semiotic_systems"})


@dataclass(frozen=True)
class Evidence:
    """One citable item this turn's tools returned, in the shape
    `agent/fact_check.py`'s prompt needs to judge a claim against: not just
    the `grounding_id` a citation would name, but the text a claim would
    have to actually be supported by."""

    grounding_id: str
    source: str
    locator: str
    text: str


def _safe_json_loads(content: object) -> object:
    try:
        return json.loads(content)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def only_listing_tools_called(tool_messages: list[ToolMessage]) -> bool:
    """True when every tool call this turn was a plain enumeration with no
    `citations` field to ever back a marker (`tools/list_signs.py` et al.) —
    the one case where a marker the model attaches anyway is a formatting
    slip on real, tool-derived data rather than an ungrounded claim FR-AG-06
    requires rejecting."""
    return bool(tool_messages) and all(message.name in _LISTING_TOOL_NAMES for message in tool_messages)


def evidence_from_get_sign_payload(payload: dict) -> list[Evidence]:
    """`get_sign`'s own citable items — one per manifestation citation
    (`agent/tools/_shared.py::_render_graph_facts`). A citation entry there
    carries only its own bibliographic `source`/`locator`, never text of its
    own — it backs the manifestation's `denotation`/`interpretants` as a
    whole, not any one sentence, so every citation for one `get_sign` call
    shares the same evidence text: the manifestation's actual descriptive
    content, which is what a claim would need to be checked against."""
    if "error" in payload:
        return []
    interpretants = "; ".join(i["value"] for i in payload.get("interpretants", ()))
    text = payload.get("denotation") or ""
    if interpretants:
        text = f"{text} Interpretants: {interpretants}." if text else f"Interpretants: {interpretants}."
    return [
        Evidence(grounding_id=c["grounding_id"], source=c["source"], locator=c["locator"], text=text)
        for c in payload.get("citations", ())
    ]


def evidence_from_query_sign_payload(payload: dict) -> list[Evidence]:
    """`query_sign`'s own citable items — one per region's segment
    (`agent/tools/_shared.py::_render_regions`), the segment's own verbatim
    text rather than the region's aggregate fields."""
    if "error" in payload:
        return []
    return [
        Evidence(grounding_id=seg["grounding_id"], source=region["source"], locator=seg["locator"], text=seg["text"])
        for region in payload.get("regions", ())
        for seg in region.get("segments", ())
    ]


def evidence_from_segments_payload(payload: list) -> list[Evidence]:
    """`fetch_segments`' own citable items — a flat list of segments, the
    same shape `evidence_from_query_sign_payload` reads per-region. Unlike a
    `query_sign` region, a bare segment here carries no parent source title
    of its own (`source_id` is a call argument, not part of the result), so
    `section` — the segment's own structural label — stands in for it."""
    return [
        Evidence(
            grounding_id=seg["grounding_id"],
            source=seg.get("section") or seg["locator"],
            locator=seg["locator"],
            text=seg["text"],
        )
        for seg in payload
        if "error" not in seg
    ]


def evidence_from_tool_messages(tool_messages: list[ToolMessage]) -> list[Evidence]:
    """Every citable item this turn's `get_sign`, `query_sign`, and
    `fetch_segments` tool results carry, dispatched by tool name to the
    payload-level readers above — the only function in this module that
    knows about `ToolMessage`, so the conversational graph path is the only
    caller that needs it. A turn that called none of these three tools (or
    only enumeration tools) yields an empty list."""
    evidence: list[Evidence] = []
    for message in tool_messages:
        payload = _safe_json_loads(message.content)
        if message.name == "get_sign" and isinstance(payload, dict):
            evidence.extend(evidence_from_get_sign_payload(payload))
        elif message.name == "query_sign" and isinstance(payload, dict):
            evidence.extend(evidence_from_query_sign_payload(payload))
        elif message.name == "fetch_segments" and isinstance(payload, list):
            evidence.extend(evidence_from_segments_payload(payload))
    return evidence


def grounding_ids(tool_messages: list[ToolMessage]) -> set[str]:
    """Every opaque `grounding_id` (ADR-022) this turn's `get_sign`,
    `query_sign`, and `fetch_segments` tool results carry — read directly off
    each item rather than reconstructed from position."""
    valid_ids: set[str] = set()
    for message in tool_messages:
        payload = _safe_json_loads(message.content)
        if message.name == "get_sign" and isinstance(payload, dict) and "error" not in payload:
            for citation in payload.get("citations", ()):
                valid_ids.add(citation.get("grounding_id"))
        elif message.name == "query_sign" and isinstance(payload, dict) and "error" not in payload:
            for region in payload.get("regions", ()):
                for segment in region.get("segments", ()):
                    valid_ids.add(segment.get("grounding_id"))
        elif message.name == "fetch_segments" and isinstance(payload, list):
            for segment in payload:
                if "error" in segment:
                    continue
                valid_ids.add(segment.get("grounding_id"))
    return valid_ids
