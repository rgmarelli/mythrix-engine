# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The `list_semiotic_systems` tool."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.core.bootstrap import Stores


def build_list_semiotic_systems_tool(stores: Stores):
    @tool
    def list_semiotic_systems() -> list[str]:
        """List the available semiotic systems (top-level sign domains,
        e.g. "tarot", "hebrew_alef_bet"). Call this and ask the user which one
        to use before listing signs/traditions or getting/querying a sign
        whenever the semiotic system is ambiguous."""
        return list(stores.graph_store.list_semiotic_systems())

    return list_semiotic_systems
