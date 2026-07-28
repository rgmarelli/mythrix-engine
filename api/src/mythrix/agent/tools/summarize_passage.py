"""The `summarize_passage` tool."""

from __future__ import annotations

from langchain_core.tools import tool

from mythrix.agent.prompts import render_passage_summary_prompt
from mythrix.agent.tools._shared import _error
from mythrix.core.chat import ChatClient
from mythrix.core.errors import MythrixError


def build_summarize_passage_tool(chat_client: ChatClient):
    @tool
    def summarize_passage(passage_text: str, concepts: list[str]) -> dict:
        """Produce a single-turn summary of an already-retrieved passage,
        scoped to the given interpretant concepts, using the generation
        model. Only call this on text a previous tool call actually returned."""
        try:
            summary = chat_client.invoke(render_passage_summary_prompt(passage_text, tuple(concepts)))
        except MythrixError as exc:
            return _error(exc)
        return {"summary": summary}

    return summarize_passage
