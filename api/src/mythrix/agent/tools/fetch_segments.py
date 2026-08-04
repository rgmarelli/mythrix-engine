# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The `fetch_segments` tool."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.agent.tools._shared import _error, _new_grounding_id
from mythrix.core.bootstrap import Stores
from mythrix.core.errors import MythrixError
from mythrix.core.query_service import fetch_source_segments


def build_fetch_segments_tool(stores: Stores):
    @tool
    def fetch_segments(source_id: str, start_ordinal: int, end_ordinal: int) -> list[dict]:
        """Read a contiguous ordinal range of one source's segments verbatim,
        by structural coordinate — no similarity search. Use this to show the
        text surrounding a region a query returned."""
        try:
            segments = fetch_source_segments(
                source_id=source_id,
                start_ordinal=start_ordinal,
                end_ordinal=end_ordinal,
                graph_store=stores.graph_store,
                vector_store=stores.vector_store,
            )
        except MythrixError as exc:
            return [_error(exc)]
        return [
            {
                "ordinal": seg.ordinal,
                "locator": seg.locator,
                "section": seg.section,
                "text": seg.text,
                "grounding_id": _new_grounding_id("S"),
            }
            for seg in segments
        ]

    return fetch_segments
