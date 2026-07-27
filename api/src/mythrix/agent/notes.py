"""Cleanup pass over the model's raw reply before it reaches the chat UI:
stripping markdown decoration the model adds despite being told not to
(small local models don't reliably follow that instruction) — the UI renders
`reply_text` as plain text, so unstripped `**bold**`/`- ` markers would show
up as literal characters."""

from __future__ import annotations

import re

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_BULLET = re.compile(r"^[ \t]*[-*][ \t]+", re.MULTILINE)


def strip_markdown(text: str) -> str:
    """Removes bold/heading/bullet markdown syntax, leaving the underlying
    prose (and its line breaks) intact — a defensive pass, not a full
    markdown parser, since it only targets the decoration this agent's
    models are actually observed to add."""
    text = _BOLD.sub(r"\1", text)
    text = _HEADING.sub("", text)
    text = _BULLET.sub("", text)
    return text
