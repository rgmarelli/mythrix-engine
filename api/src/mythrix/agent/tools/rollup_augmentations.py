"""The `rollup_augmentations` tool — node-only (ADR-015, ADR-016)."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.agent.prompts import render_rollup_prompt
from mythrix.agent.tools._shared import _generated
from mythrix.core.chat import ChatClient


def build_rollup_augmentations_tool(chat_client: ChatClient):
    @tool
    def rollup_augmentations(focus: str, summaries: list[str]) -> dict:
        """Combine several already-synthesized analyses — each already citing
        regions via [R#] markers embedded in its own text — into one further
        synthesis, preserving every such marker verbatim. Used above the first
        consolidation level of a hierarchical run (ADR-016). Reachable only
        from a deterministic node."""
        return _generated(chat_client, render_rollup_prompt(focus, tuple(summaries)), "consolidation")

    return rollup_augmentations
