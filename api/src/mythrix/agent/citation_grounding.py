# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Reads a citable tool result's own opaque `grounding_id`s (ADR-022) off
`get_sign`/`query_sign`/`fetch_segments` payloads — the shared core both
`turn_service.py`'s post-hoc check and the in-graph citation-retry node
(`graph/nodes/citation_check.py`, ADR-023) build on.

Deliberately narrower than `turn_service.py::_build_valid_marker_ids`: it
knows nothing about `augment_regions`' `[R#]` region labels, a distinct,
position-based id space (FR-AU-30) only `/augment` produces — that branch
stays in `turn_service.py`, the only caller that still needs it.

Kept separate from `agent/citations.py`, which is deliberately typeless
(works on text and a caller-supplied id set, never on tool payloads), and
from `turn_service.py`, a higher-level orchestrator that composes the graph
rather than something the graph should depend on — this module sits below
both.
"""

from __future__ import annotations

import json

from langchain_core.messages import ToolMessage

_LISTING_TOOL_NAMES = frozenset({"list_signs", "list_traditions", "list_semiotic_systems"})


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


def uncited_valid_ids(cited_markers: set[str], valid_ids: set[str]) -> set[str]:
    """The valid ids belonging to a distinct grounding-id prefix (`G` from
    `get_sign`, `S` from `query_sign`/`fetch_segments`, ADR-022) that
    `cited_markers` cites none of. A turn calling more than one citable tool
    must cite from each one's results, not just one of them — citing only
    the `get_sign` fact while silently dropping every `query_sign` marker
    leaves that tool's evidence exactly as ungrounded as citing nothing at
    all would (FR-CR-11, generalizes FR-CR-07's all-or-nothing check to
    per-prefix coverage). Returns only the ids still needing a citation, not
    every valid id, so the retry pushback can point at exactly what's
    missing."""
    cited_prefixes = {marker[0] for marker in cited_markers if marker}
    return {valid_id for valid_id in valid_ids if valid_id and valid_id[0] not in cited_prefixes}


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
