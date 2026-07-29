"""The operator system prompt (specs/interfaces/agent.md FR-AG-05, FR-AG-06,
FR-AG-09), which defines the `[G#]`/`[S#]` marker vocabulary `citations.py`
validates against, plus the ad-hoc prompts the generative tools render.

Each renderable prompt belongs to exactly one tool. They deliberately do not
share a template: a summary of a selected passage, a reading of a retrieved
passage against a user's question, and a consolidation across readings differ
in what they are allowed to use and what they must say when they have nothing
to say (ADR-015)."""

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

def render_passage_analysis_prompt(text: str, focus: str, concepts: tuple[str, ...]) -> str:
    return (
        f"Analyze the following passage for this analytical task: {focus}\n\n"
        "Base your analysis exclusively on the passage itself. "
        "Interpret the passage directly and make reasonable inferences "
        "when they are supported by the text. "
        "Do not introduce external facts or context.\n\n"
        "If the passage provides relevant evidence for the requested analysis, "
        "describe it. If the evidence is ambiguous, explain the ambiguity. "
        "Only say that the passage is not relevant when it genuinely provides "
        "no basis for the requested analysis.\n\n"
        f'Passage:\n"{text}"'
    )

def render_discovery_consolidation_prompt(
    focus: str, findings: tuple[tuple[str, str], ...], concepts: tuple[str, ...]
) -> str:
    rendered = "\n\n".join(
        f"{label}\n{finding}" for label, finding in findings
    )

    return (
        "The user requested the following analysis:\n\n"
        f"{focus}\n\n"
        "The passages were analyzed independently. "
        "Below are the resulting analyses, each identified by its region label.\n\n"
        f"{rendered}\n\n"
        "Synthesize these analyses to answer the requested analytical task. "
        "Do not replace the requested analysis with a relevance check, "
        "keyword comparison, or search summary. "
        "Do not assume that the retrieval terms are the subject of the analysis. "
        "Report the patterns, differences, and relevant evidence that emerge "
        "from the individual analyses. "
        "If the passages genuinely provide little or no evidence for the task, "
        "say so, but do not infer irrelevance merely because the requested "
        "analysis is not explicitly mentioned in the passages.\n\n"
        "Use only the analyses above. "
        "Cite the regions supporting each claim by their label in square brackets, "
        "e.g. [R1] or [R1][R3]. "
        "Never cite a label that does not appear above."
    )
