# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The operator system prompt (specs/interfaces/agent.md FR-AG-05, FR-AG-06,
FR-AG-09), plus the ad-hoc prompts the generative tools render, including
the fact-check prompt (ADR-025) that defines the `[G#]`/`[S#]`/`[UNSUPPORTED]`
marker vocabulary `citations.py` validates against — the primary model's own
prompt asks for none of it; grounding is checked after the fact, not
composed inline (ADR-025).

Each renderable prompt belongs to exactly one tool. They deliberately do not
share a template: a summary of a selected passage, a reading of a retrieved
passage against a user's question, and a consolidation across readings differ
in what they are allowed to use and what they must say when they have nothing
to say (ADR-015)."""

from __future__ import annotations

import json

from mythrix.agent.citation_grounding import Evidence, strip_grounding_prefix

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


def render_fact_check_prompt(evidence: tuple[Evidence, ...], sentences: tuple[str, ...]) -> str:
    """The fact-checking model's own prompt (ADR-025) — a second, narrow call
    made after the primary model's answer is already final, classifying it
    against this turn's evidence.

    The model receives a JSON document with one entry per sentence
    (`fact_check.split_sentences`, done deterministically in code) — each
    entry already carrying its own `index` and `text` — and completes it,
    replacing only `supported` and populating `citations` per entry.
    `index`/`text` must not be modified, and no field or object may be
    added, removed, reordered, or renamed. `graph/nodes/fact_check.py`
    parses the response into verdicts keyed by `index` alone; an entry's
    echoed `text` is read by nobody downstream, so a model that drifts on
    that field cannot desync what a verdict is actually attributed to.

    The evidence block carries only an item's id and text, not its
    `source`/`locator` — those fields still live on `Evidence` for other
    consumers. The id itself is shown without its origin-tagging prefix
    letter (`strip_grounding_prefix`, ADR-022) — the letter is a
    human/log-reading mnemonic no consumer branches on, so there is nothing
    for the model to lose by not seeing it, and one fewer character per id
    to read and echo back. `graph/nodes/fact_check.py` builds the valid-id
    set the same way, so a citation compares against what the model was
    actually shown.

    A faithful summary or reasonable paraphrase of the evidence counts as
    supported; `supported: false` is reserved for a sentence that introduces
    new information or an interpretation not reasonably supported by the
    evidence — not merely a departure from its exact wording."""
    verification_json = json.dumps(
        {
            "results": [
                {"index": i, "text": sentence, "supported": None, "citations": []}
                for i, sentence in enumerate(sentences)
            ]
        },
        indent=2,
    )
    rendered_evidence = "\n\n".join(f"[{strip_grounding_prefix(e.grounding_id)}]\n{e.text}" for e in evidence)
    return (
        "You are a factual verification assistant.\n\n"
        "You are given:\n\n"
        "1. A JSON document containing sentences.\n"
        "2. A list of Evidence items, each identified by a unique id.\n\n"
        "Your task is to complete the JSON.\n\n"
        'For each object in "results":\n\n'
        '- Read the value of "text".\n'
        "- Determine whether the factual claims in the text are supported by the provided Evidence.\n"
        "- Faithful summaries and reasonable paraphrases of the Evidence are considered supported.\n"
        "- Do NOT require identical wording.\n"
        "- Mark a sentence as unsupported ONLY if it introduces new factual information or interpretations "
        "that are not reasonably supported by the Evidence.\n"
        "- Use ONLY the provided Evidence. Never use outside knowledge.\n\n"
        "Rules:\n\n"
        "- Do NOT add, remove, reorder, or rename any objects or fields.\n"
        '- Do NOT modify the values of "index" or "text".\n'
        '- Only replace the value of "supported".\n'
        '- Only populate the "citations" array.\n'
        "- A sentence with no factual claims should have:\n"
        '    "supported": null\n'
        '    "citations": []\n'
        "- A supported sentence must have:\n"
        '    "supported": true\n'
        '    "citations": ["...", ...]\n'
        "- An unsupported sentence must have:\n"
        '    "supported": false\n'
        '    "citations": []\n\n'
        "Every citation id must exist in the Evidence.\n"
        "Never invent citation ids.\n\n"
        "Return ONLY the completed JSON.\n\n"
        f"JSON:\n\n{verification_json}\n\n"
        f"Evidence:\n\n{rendered_evidence}"
    )
