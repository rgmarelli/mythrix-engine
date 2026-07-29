"""The `summarize_passage` tool."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.agent.prompts import render_passage_summary_prompt
from mythrix.agent.tools._shared import _generated
from mythrix.core.chat import ChatClient


def build_summarize_passage_tool(chat_client: ChatClient):
    @tool
    def summarize_passage(passage_text: str, concepts: list[str]) -> dict:
        """Produce a single-turn summary of an already-retrieved passage,
        scoped to the given interpretant concepts, using the generation
        model. Only call this on text a previous tool call actually returned."""
        return _generated(chat_client, render_passage_summary_prompt(passage_text, tuple(concepts)), "summary")

    return summarize_passage
