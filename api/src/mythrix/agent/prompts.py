# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

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
- If an "Active hotspot" is present in context (e.g., Active hotspot: source_id::start-end), immediately call `fetch_segments` using those exact parameters. Do not ask for clarification.
- Once segments for the requested hotspot/passage are retrieved, assume they contain ENOUGH context to answer the user's question. DO NOT attempt to fetch adjacent segments unless explicitly requested by the user.
- Use `get_sign` for sign structure/traditions.
- Use `query_sign` for textual evidence across corpus.

Response rules:
- Ground all analysis, explanations, or sentiments strictly and EXCLUSIVELY on the text returned by tools in the current thread.
- Each tool result item carries its own grounding id. End every sentence that references, quotes, or analyzes that item with its id in square brackets, e.g. "The Sun symbolizes joy and vitality [G4f9a2c]." Never cite a source name or page number instead of the bracketed id — the bracketed id is the only valid citation. Never invent, renumber, or reuse an id of your own.
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


def render_augmentation_prompt(text: str, focus: str, source: str, locator: str) -> str:
    """One region's reading against the user's own question (FR-AU-19).

    The reference (`source`/`locator`) is included so the model never has to
    infer what passage it is reading — a gap that, left open, does not stay
    unfilled: the model recognizes familiar text from its own training and
    states a reference for it anyway, sometimes the wrong one. The instruction
    below is deliberately narrow — ground the reading, do not editorialize
    from it — since knowing the true reference should not license answering
    from anything beyond the passage's own text.

    The retrieval terms remain absent, unlike the reference: a region reaches
    a run because the user is looking at it, not because a term matched, so
    naming a term here would invite the model to answer about it instead of
    about the focus. A reference is not a retrieval term — it identifies the
    passage rather than explaining why it was surfaced."""
    return (
        f"Reference: {source} — {locator}.\n\n"
        f"Analyze the following passage for this analytical task: {focus}\n\n"
        "Base your analysis exclusively on the passage itself. "
        "Interpret the passage directly and make reasonable inferences "
        "when they are supported by the text. "
        "Do not introduce external facts or context.\n\n"
        "The reference above identifies which passage this is. Use it only "
        "for that. Do not name, restate, or discuss the reference itself, and "
        "do not draw on outside or prior knowledge associated with it — "
        "everything you say must still come from the passage's own text.\n\n"
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


def render_citation_pushback(invalid_markers: tuple[str, ...]) -> str:
    """The corrective message `graph/nodes/citation_check.py::validate_citations_node`
    injects when the model's reply cites a marker no tool result this turn
    actually carries (ADR-023) — delivered as a `HumanMessage`, giving the
    model a bounded number of chances to fix it before the turn falls back to
    `citations.py::CITATION_FAILURE_MESSAGE`. Names the specific marker(s) at
    fault rather than restating the citation rule in the abstract, since the
    model has already seen that rule once this turn and evidently didn't
    apply it — repeating it unchanged is less likely to help than pointing at
    exactly what was wrong.

    Explicitly says the answer's *content* was fine and only the marker needs
    fixing: real-model retries (`qwen3:1.7b`, ADR-023) showed that a pushback
    focused only on the marker can read as "give me the id," collapsing a
    full answer into a bare id list on retry — which then fails validation
    again for having no prose to attach a citation to, burning the retry
    budget on a reply that was never going to pass."""
    return (
        f"Your last answer's content was fine — only the citation needs fixing. It used a citation "
        f"marker that doesn't match any tool result from this turn: {', '.join(invalid_markers)}. Repeat "
        f"the same answer in full, in full sentences, replacing the wrong marker(s) with the correct "
        f"grounding ids shown in the tool results above — each id in its own square brackets, e.g. "
        f"[id1] [id2], never [id1, id2]. Do not invent, renumber, or omit them, and do not shorten your "
        f"answer to a bare list of ids."
    )


def render_missing_citation_pushback(uncited_ids: set[str]) -> str:
    """The corrective message `validate_citations_node` injects when the
    model's reply leaves some of this turn's citable grounding ids
    uncited — whether it cited nothing at all, or cited one tool's results
    while silently dropping another's (ADR-023, FR-CR-07/08/11) — the
    counterpart to `render_citation_pushback` for omission rather than a
    wrong marker. Lists only the ids still needing a citation, not every
    valid id, for the same reason `render_citation_pushback` names the
    specific marker at fault.

    Same "content was fine, only the citation needs fixing" framing as
    `render_citation_pushback`, and the same warning against collapsing to a
    bare id list — see that docstring for the observed failure mode."""
    ids = ", ".join(f"[{marker_id}]" for marker_id in sorted(uncited_ids))
    return (
        f"Your last answer's content was fine — only the citation needs fixing. It left some of this "
        f"turn's citable items uncited: {ids}. Repeat the same answer in full, in full sentences, and add "
        f"a citation for the claim(s) that draw on {ids} — each id in its own square brackets, e.g. "
        f"[id1] [id2], never [id1, id2]. Do not shorten your answer to a bare list of ids."
    )
