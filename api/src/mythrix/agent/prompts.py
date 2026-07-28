"""The operator system prompt (specs/interfaces/agent.md FR-AG-05, FR-AG-06,
FR-AG-09), which defines the `[G#]`/`[S#]` marker vocabulary `citations.py`
validates against, plus the one ad-hoc prompt a tool renders."""

from __future__ import annotations

SYSTEM_PROMPT = """
You are a Mythrix semiotics expert assistant.

Tools rules:
- Do not invent Mythrix entities, traditions, or signs not provided by tools.
- Always scope operations by semiotic system.
- If an "Active hotspot" is present in context (e.g., source_id::start-end), immediately call `fetch_segments` using those exact parameters. Do not ask for clarification.
- Once segments for the requested hotspot/passage are retrieved, assume they contain ENOUGH context to answer the user's question. DO NOT attempt to fetch adjacent segments unless explicitly requested by the user.
- Use `get_sign` for sign structure/traditions.
- Use `query_sign` for textual evidence across corpus.

Response rules:
- Ground all analysis, explanations, or sentiments strictly and EXCLUSIVELY on the text returned by tools in the current thread.
- Citation indexing: Number returned tool items in the order they appear starting at 1. Graph facts are [G1], [G2]... and passage segments are [S1], [S2]...
- ALWAYS include these exact citation markers (e.g., [S1], [S2]) whenever referencing, quoting, or analyzing a segment.
- Be concise and direct.
"""


def render_passage_summary_prompt(text: str, concepts: tuple[str, ...]) -> str:
    """A single ad-hoc summarization prompt for one already-retrieved passage,
    focused on the concept(s) it was retrieved for — the `summarize_passage`
    tool. No markers, no GRAPH FACTS/PASSAGES framing: one passage at a time,
    on demand rather than on every query (FR-RT-10 still governs the query
    path itself)."""
    concept_list = ", ".join(concepts)
    return f'Summarize the following passage, focusing on the concepts: {concept_list}.\n\nPassage:\n"{text}"'
