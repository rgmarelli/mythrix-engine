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

from mythrix.agent.citation_grounding import Evidence

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

    Unlike every earlier draft of this prompt, the model is never given the
    answer as text to reproduce: it receives the answer pre-split into
    numbered sentences (`fact_check.split_sentences`, done deterministically
    in code) and returns a JSON classification keyed by sentence index —
    never the sentences' own text. Six distinct real-model failure shapes
    (an appended closing remark, a deleted clause, a duplicated/reordered
    clause, reformatted markdown, an echoed evidence block, and a lost
    citation clause) were all found while hardening an earlier
    reproduce-and-tag design; every one of them was a way of getting the
    reproduction task wrong, and none of them is possible against a task
    that has no reproduction step in it. `graph/nodes/fact_check.py` parses
    the response into structured verdicts and scores them in code — the
    model's own `verified` field is never read, only `results`.

    The evidence block deliberately carries only an item's id and text, not
    its `source`/`locator` — a smaller prompt for the model to reason over;
    those fields still live on `Evidence` for other consumers.

    Framed as hallucination detection, not literal-wording verification
    (user-directed revision, 2026-08-05): a first draft asked whether each
    sentence was "fully supported" by the evidence, which real-model testing
    (`phi4-mini`) found punished faithful paraphrase and summary — a
    plausible restatement of an evidence item, not a fabricated claim, was
    scored unsupported for not matching the evidence's own wording closely
    enough. The instructions now explicitly accept a faithful summary or
    reasonable paraphrase as supported, and reserve `unsupported` for a
    sentence that introduces information, an interpretation stated as fact,
    or a conclusion the evidence does not reasonably support — closer to
    what "hallucination" actually means for this check.

    Completeness contract, added the same day (user-directed): real-model
    output kept silently dropping an index from `results` entirely — not
    marking it unsupported, just omitting it, which `_parse_verdicts`
    tolerates by design but which quietly undercounts what the answer
    actually claimed. The original schema's "omit sentences with no factual
    claims" instruction gave the model an easy excuse to omit *any*
    sentence it found awkward, not just a genuine non-claim one — a
    sentence fragmented by a citation abbreviation (`"(p."`/`"143),..."`,
    the bug `fact_check.py::split_sentences`'s digit-lookahead fix now
    prevents) got silently skipped rather than classified. The schema now
    requires exactly one result per sentence, in order, replacing the old
    omit-if-no-claim instruction with an explicit `"claim": false` value —
    still excluded from scoring (`_parse_verdicts` skips a `"claim": false`
    entry the same way it used to skip an absent one), but now a positive
    statement the model must make for every index rather than a silent
    non-appearance the model could default into for any sentence."""
    rendered_sentences = "\n".join(f"{i}. {s}" for i, s in enumerate(sentences))
    rendered_evidence = "\n\n".join(f"[{e.grounding_id}]\n{e.text}" for e in evidence)
    count = len(sentences)
    return (
        "You are a hallucination detector.\n\n"
        "Input:\n"
        "- Sentences\n"
        "- Evidence items (each has an id)\n\n"
        "Task:\n"
        "For each sentence, first decide whether it contains a factual claim at all "
        "(a greeting, a question, or a transition does not).\n"
        "For each sentence that contains one or more factual claims:\n\n"
        "- Determine whether the sentence is a faithful representation of the provided Evidence.\n"
        "- Faithful summaries and reasonable paraphrases are considered supported.\n"
        "- Do NOT require identical wording.\n"
        "- Do NOT use outside knowledge.\n"
        "- Mark a sentence as unsupported ONLY if it introduces new factual information, interpretations "
        "presented as facts, or conclusions that cannot be reasonably inferred from the Evidence.\n\n"
        f"There are {count} input sentences below. Return EXACTLY {count} results, in the same order. "
        'For sentence i, result i MUST have "index": i. Do not omit any sentence.\n\n'
        "Return ONLY valid JSON:\n\n"
        "{\n"
        '  "verified": true,\n'
        '  "results": [\n'
        "    {\n"
        '      "index": 0,\n'
        '      "claim": true,\n'
        '      "supported": true,\n'
        '      "citations": ["S48eda8"]\n'
        "    },\n"
        "    {\n"
        '      "index": 1,\n'
        '      "claim": false\n'
        "    },\n"
        "    {\n"
        '      "index": 2,\n'
        '      "claim": true,\n'
        '      "supported": false\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- The index refers to the sentence number.\n"
        f"- There are {count} input sentences. Return exactly {count} results, one per sentence, in the same "
        'order. Result i MUST have "index": i. Never omit a sentence, even one you are unsure about.\n'
        '- Set "claim": false for a sentence with no factual claim (a greeting, a question, a transition) '
        'and omit "supported"/"citations" for it.\n'
        '- Set "claim": true for a sentence with one or more factual claims, and set "supported" per the '
        "Task rules above.\n"
        "- A sentence may cite multiple evidence ids.\n"
        "- Every citation id must exist in the Evidence.\n"
        "- Never invent citation ids.\n"
        '- Set "verified" to false if any sentence is unsupported.\n'
        "- Return JSON only.\n\n"
        f"Sentences:\n\n{rendered_sentences}\n\n"
        f"Evidence:\n\n{rendered_evidence}"
    )
