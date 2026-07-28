"""The agent's fixed, read-only tool set (specs/interfaces/agent.md FR-AG-03, FR-AG-04) — every
tool is a thin wrapper over an existing Mythrix service function; none of this
package implements retrieval, graph, embedding, or synthesis logic of its own.
Each tool lives in its own module; helpers shared across tool modules live in
`_shared.py`.

`build_tools` closes over an already-built `Stores`, `Settings`, and
`ChatClient` (constructed once by `api/dependencies.py`) instead of holding
module-level globals, so the tool set is trivially fakeable in tests and is
rebuilt fresh per process rather than shared mutable state.

Each tool returns compact, JSON-serializable data (dicts / lists of dicts) —
never prose — so the LLM relays cited evidence rather than inventing it
(FR-AG-06). A `MythrixError` raised while a tool runs (unknown sign/tradition/source,
an unreachable model) is caught here and turned into a structured `{"error":
...}` result instead of propagating, so a bad tool call becomes a recoverable
turn (FR-AG-11) rather than crashing the graph.
"""

from __future__ import annotations

from mythrix.agent.tools.fetch_segments import build_fetch_segments_tool
from mythrix.agent.tools.get_sign import build_get_sign_tool
from mythrix.agent.tools.list_semiotic_systems import build_list_semiotic_systems_tool
from mythrix.agent.tools.list_signs import build_list_signs_tool
from mythrix.agent.tools.list_traditions import build_list_traditions_tool
from mythrix.agent.tools.query_sign import build_query_sign_tool
from mythrix.agent.tools.summarize_passage import build_summarize_passage_tool
from mythrix.core.bootstrap import Stores
from mythrix.core.chat import ChatClient
from mythrix.core.config import Settings


def build_tools(stores: Stores, settings: Settings, chat_client: ChatClient) -> list:
    """Returns the seven read-only tools the agent may call
    (specs/interfaces/agent.md FR-AG-03). The registered set contains no `upsert_*`, `load_*`, or reload
    operation — read-only is a structural property of this list, not a
    runtime check (FR-AG-04)."""
    return [
        build_list_semiotic_systems_tool(stores),
        build_list_traditions_tool(stores),
        build_list_signs_tool(stores),
        build_get_sign_tool(stores),
        build_query_sign_tool(stores, settings),
        build_fetch_segments_tool(stores),
        build_summarize_passage_tool(chat_client),
    ]
