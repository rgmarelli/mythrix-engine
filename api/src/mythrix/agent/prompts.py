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


def render_augmentation_prompt(text: str, focus: str) -> str:
    """One region's reading against the user's own question (FR-AU-19).

    The retrieval terms are deliberately absent: a region reaches a run
    because the user is looking at it, not because a term matched, so naming
    terms here would invite the model to answer about them instead of about
    the focus."""
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


def render_consolidation_prompt(focus: str, augmentations: tuple[tuple[str, str], ...]) -> str:
    """The single answer across a run's augmentations (FR-AU-20). Given the
    augmentations and their labels only — never raw passage text, which this
    invocation has no way to cite and no need to re-read."""
    rendered = "\n\n".join(f"{label}\n{augmentation}" for label, augmentation in augmentations)

    return (
        "The user requested the following analysis:\n\n"
        f"{focus}\n\n"
        "The passages were analyzed independently. "
        "Below are the resulting analyses, each identified by its region label.\n\n"
        f"{rendered}\n\n"
        "Synthesize these analyses to answer the requested analytical task. "
        "Do not replace the requested analysis with a relevance check, "
        "keyword comparison, or search summary. "
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


def render_rollup_prompt(focus: str, summaries: tuple[str, ...]) -> str:
    """A further synthesis across summaries that are themselves consolidations
    (FR-AU-39), used above the first consolidation level once a run has more
    augmentations than one invocation may be given (ADR-016).

    Unlike `render_consolidation_prompt`, these inputs are not individually
    labeled — each already cites the regions behind it with `[R#]` markers
    embedded in its own text. This prompt's one load-bearing instruction is
    therefore the opposite of the leaf prompt's: carry every such marker
    forward exactly as written rather than choosing from a label list, since
    inventing or renumbering one here would cite a region this invocation was
    never given."""
    rendered = "\n\n".join(f"Summary {i}:\n{summary}" for i, summary in enumerate(summaries, start=1))

    return (
        "The user requested the following analysis:\n\n"
        f"{focus}\n\n"
        "Below are several analyses, each already synthesized from a group of "
        "readings and already citing the specific regions behind it using "
        "[R#] markers embedded in its own text.\n\n"
        f"{rendered}\n\n"
        "Synthesize these summaries into one further analysis that answers the "
        "requested analytical task, describing what recurs and what diverges "
        "across them.\n\n"
        "Every [R#] marker already present in the summaries above must appear "
        "in your answer exactly as written, unchanged, wherever the claim it "
        "supports survives or is paraphrased. Never invent a new marker, never "
        "renumber one, and never merge two into one. The 'Summary N' labels "
        "above are for your reference only, are not citation markers, and must "
        "not appear in your answer."
    )
