"""The `consolidate_findings` tool — node-only (ADR-015)."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.agent.prompts import render_discovery_consolidation_prompt
from mythrix.agent.tools._shared import _generated
from mythrix.core.chat import ChatClient


def build_consolidate_findings_tool(chat_client: ChatClient):
    @tool
    def consolidate_findings(focus: str, findings: list[dict], concepts: list[str]) -> dict:
        """Answer a question across every reading a discovery run produced,
        naming what recurs and where the readings diverge. Each finding
        carries a `label` and a `finding`; no passage text is given, so this
        reports on the readings alone. Reachable only from a deterministic
        node."""
        labeled = tuple((finding["label"], finding["finding"]) for finding in findings)
        return _generated(
            chat_client,
            render_discovery_consolidation_prompt(focus, labeled, tuple(concepts)),
            "consolidation",
        )

    return consolidate_findings
