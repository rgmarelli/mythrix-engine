# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The `list_signs` tool."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.core.bootstrap import Stores


def build_list_signs_tool(stores: Stores):
    @tool
    def list_signs(semiotic_system: str | None = None) -> list[dict]:
        """List available signs, optionally scoped to one semiotic
        system. Each entry includes the traditions the sign is manifested in."""
        return [
            {
                "slug": sign.slug,
                "name": sign.canonical_name,
                "semiotic_system": sign.semiotic_system,
                "traditions": list(sign.tradition_slugs),
            }
            for sign in stores.graph_store.list_signs()
            if semiotic_system is None or sign.semiotic_system == semiotic_system
        ]

    return list_signs
