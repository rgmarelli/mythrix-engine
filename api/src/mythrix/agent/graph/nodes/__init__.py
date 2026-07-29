# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""LangGraph node implementations, grouped by which command/turn shape they
handle: `adhoc` (`/query`, `/query-confirm`), `summary` (`/summarize`), and
`llm` (the model-driven agent turn and its clarify/routing helpers)."""
