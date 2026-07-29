# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The `read_region` tool — node-only (ADR-015)."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.agent.tools._shared import _error
from mythrix.core.bootstrap import Stores
from mythrix.core.errors import MythrixError
from mythrix.core.query_service import fetch_source_segments
from mythrix.core.retrieval.pipeline import parse_region_id, region_locator


def build_read_region_tool(stores: Stores):
    @tool
    def read_region(region_id: str) -> dict:
        """Read one region's identity and full verbatim passage from its
        structural identity alone. Reachable only from a deterministic node.

        Every attribute but the identity is derived here rather than accepted
        from a caller (FR-AU-15), so a consumer supplying a region cannot
        influence how it is attributed or what text is read for it."""
        try:
            source_id, start_ordinal, end_ordinal = parse_region_id(region_id)
        except ValueError as exc:
            return {"error": str(exc)}

        try:
            source = stores.graph_store.get_source(source_id)
            segments = fetch_source_segments(
                source_id=source_id,
                start_ordinal=start_ordinal,
                end_ordinal=end_ordinal,
                graph_store=stores.graph_store,
                vector_store=stores.vector_store,
            )
        except MythrixError as exc:
            return _error(exc)

        if not segments:
            return {"error": f"no segments for region {region_id!r}"}

        # The whole ordinal range, matching or not: a region carries only its
        # match-carrying ordinals, so joining those would hand the passage to
        # the model with holes in it (FR-AU-17).
        return {
            "region_id": region_id,
            "source": source.citation_label or source.title,
            "source_id": source_id,
            "locator": region_locator(segments),
            "text": "\n\n".join(segment.text for segment in segments),
        }

    return read_region
