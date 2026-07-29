# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The `list_traditions` tool."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.core.bootstrap import Stores


def build_list_traditions_tool(stores: Stores):
    @tool
    def list_traditions(semiotic_system: str | None = None) -> list[dict]:
        """List available traditions. If semiotic_system is given, only
        traditions that have at least one sign manifested in that system."""
        traditions = stores.graph_store.list_traditions()
        if semiotic_system is None:
            return [{"slug": t.slug, "name": t.name} for t in traditions]
        scoped_slugs = {
            tradition_slug
            for sign in stores.graph_store.list_signs()
            if sign.semiotic_system == semiotic_system
            for tradition_slug in sign.tradition_slugs
        }
        return [{"slug": t.slug, "name": t.name} for t in traditions if t.slug in scoped_slugs]

    return list_traditions
