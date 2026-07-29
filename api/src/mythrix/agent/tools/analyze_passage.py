"""The `analyze_passage` tool — node-only (ADR-015)."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.agent.prompts import render_passage_analysis_prompt
from mythrix.agent.tools._shared import _generated
from mythrix.core.chat import ChatClient


def build_analyze_passage_tool(chat_client: ChatClient):
    @tool
    def analyze_passage(passage_text: str, focus: str, concepts: list[str]) -> dict:
        """Read one already-retrieved passage against a free-text question,
        answering from that passage alone. The per-region step of a corpus
        discovery run; reachable only from a deterministic node."""
        return _generated(chat_client, render_passage_analysis_prompt(passage_text, focus, tuple(concepts)), "finding")

    return analyze_passage
