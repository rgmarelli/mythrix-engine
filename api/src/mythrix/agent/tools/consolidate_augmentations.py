"""The `consolidate_augmentations` tool — node-only (ADR-015)."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.agent.prompts import render_consolidation_prompt
from mythrix.agent.tools._shared import _generated
from mythrix.core.chat import ChatClient


def build_consolidate_augmentations_tool(chat_client: ChatClient):
    @tool
    def consolidate_augmentations(focus: str, augmentations: list[dict]) -> dict:
        """Answer a question across every reading an augmentation run
        produced, naming what recurs and where the readings diverge. Each
        entry carries a `label` and an `augmentation`; no passage text is
        given, so this reports on the readings alone. Reachable only from a
        deterministic node."""
        labeled = tuple((entry["label"], entry["augmentation"]) for entry in augmentations)
        return _generated(chat_client, render_consolidation_prompt(focus, labeled), "consolidation")

    return consolidate_augmentations
