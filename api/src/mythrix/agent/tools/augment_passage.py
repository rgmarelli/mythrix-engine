"""The `augment_passage` tool — node-only (ADR-015)."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.agent.prompts import render_augmentation_prompt
from mythrix.agent.tools._shared import _generated
from mythrix.core.chat import ChatClient


def build_augment_passage_tool(chat_client: ChatClient):
    @tool
    def augment_passage(passage_text: str, focus: str, source: str, locator: str) -> dict:
        """Read one region's passage against a free-text question, answering
        from that passage alone. Told the region's own source and locator so
        it never has to guess what passage it is reading. The per-region step
        of an augmentation run; reachable only from a deterministic node."""
        return _generated(chat_client, render_augmentation_prompt(passage_text, focus, source, locator), "augmentation")

    return augment_passage
