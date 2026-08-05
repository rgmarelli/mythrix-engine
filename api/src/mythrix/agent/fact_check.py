# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Post-hoc grounding for a conversational reply (ADR-025): a second, narrow
model call classifies the primary model's already-produced answer, sentence
by sentence, against this turn's tool-returned evidence — rather than asking
the primary model to cite itself while composing it, and rather than asking
the fact-checker to reproduce the answer's text at all.

The model is given the answer pre-split into numbered sentences (in code,
`split_sentences`) and returns a small JSON classification keyed by sentence
index — never the answer text itself. This is a deliberate shift from an
earlier draft of this design, which asked the fact-checker to echo the whole
answer back with tags inserted inline: real-model testing against
`qwen3:1.7b` found six distinct ways a reproduction task like that drifts
(an appended remark, a deleted clause, reordered/duplicated text, reformatted
markdown, an echoed evidence block). None of those failure modes are
possible here, by construction — the model's output never contains any of
the answer's own text, so there is nothing for it to rewrite.

Deliberately graph/LangChain-agnostic — `run_fact_check` takes and returns
plain types only (`Evidence`, defined in `agent/citation_grounding.py`
alongside the functions that build it from a tool payload, is a plain
dataclass with no LangChain dependency of its own), so a future
`/summarize`/`/augment` call site can reuse this module by building its own
evidence list from the tool results it already holds, with no dependency on
`AgentState` or `ToolMessage`.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from mythrix.agent.citation_grounding import Evidence
from mythrix.agent.prompts import render_fact_check_prompt
from mythrix.core.chat import ChatClient
from mythrix.core.errors import MythrixError
from mythrix.core.logging_config import truncate

logger = logging.getLogger(__name__)

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?!\d)")
_LIST_MARKER = re.compile(r"^[ \t]*(?:[-*+•]|\d+[.)])[ \t]+")
_MARKDOWN_DECORATION = re.compile(r"[*_`#]")
_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class SentenceVerdict:
    """One sentence's classification, as the fact-checker returned it —
    parsed from JSON, not extracted from text. `citations` is not filtered
    against a valid-id set here; that check belongs to `grounding_score`,
    the one place that already holds the evidence this turn actually has."""

    index: int
    supported: bool
    citations: tuple[str, ...] = field(default_factory=tuple)


def split_sentences(text: str) -> tuple[str, ...]:
    """Splits `text` into sentences for the fact-checker to classify by
    index — never reconstructed into the displayed reply, which is always
    the original, unsplit answer with a score footer appended, so this only
    has to be good enough to reference a claim by position, not lossless.

    A line break is itself treated as a sentence boundary, not just
    whitespace to collapse: each line is stripped of a leading list marker
    (`-`, `*`, `+`, `•`, `1.`, `2)`, ...) and markdown decoration
    (`*`/`_`/backtick/`#`), then split on its own for `.`/`!`/`?` boundaries
    — a header line with no terminal punctuation (e.g. `"Key points:"`)
    survives as its own sentence rather than fusing with the next line's
    first clause. Without the per-line marker stripping, a markdown numbered
    list fragments badly on its own: the period in a `1.`/`2.` marker reads
    as a sentence end to the boundary regex by itself, producing a garbage
    "sentence" like `"Key points:  \\n1."` — real-model output this fix is a
    direct response to (a bulleted/numbered answer sent to the fact-checker
    without it).

    The boundary itself also excludes a `.`/`!`/`?` immediately followed by
    a digit — the same regex fired inside `"(p. 143)"`, splitting a page
    citation into `"...(p."` and `"143), where it is..."`: a fragment with
    no sentence of its own, which real-model output (`phi4-mini`) then
    dropped from its classification results entirely rather than erroring,
    silently undercounting the answer's actual claims. `"p."` is not
    special-cased by name; excluding a digit right after the boundary covers
    it and every other short citation abbreviation (`pp.`, `No.`, `Vol.`,
    `Fig.`) the same way, at the acceptable cost of not splitting a genuine
    sentence that starts with a number — rare, and a false negative here
    only merges two sentences rather than fragmenting one."""
    stripped = text.strip()
    if not stripped:
        return ()
    sentences: list[str] = []
    for line in stripped.splitlines():
        cleaned = _MARKDOWN_DECORATION.sub("", _LIST_MARKER.sub("", line)).strip()
        if cleaned:
            sentences.extend(s for s in _SENTENCE_BOUNDARY.split(cleaned) if s)
    return tuple(sentences)


def _safe_json_loads(text: str) -> object:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _extract_json(text: str) -> object:
    """Tolerant JSON extraction shared by `_parse_verdicts` and `_pretty`: a
    markdown code fence around the whole response, or stray prose around a
    JSON object, is stripped before parsing (models add these despite being
    told not to, and stripping them costs nothing)."""
    candidate = _JSON_FENCE.sub("", text.strip())
    payload = _safe_json_loads(candidate)
    if payload is not None:
        return payload
    match = _JSON_OBJECT.search(candidate)
    return _safe_json_loads(match.group(0)) if match else None


def _pretty(text: str) -> str:
    """Best-effort readable form for logging: valid JSON (via `_extract_json`)
    renders indented, so a log line actually shows the model's answer instead
    of a `%r`-escaped single-line string with literal `\\n`s in it. Anything
    that isn't valid JSON logs as the model wrote it, unmodified."""
    payload = _extract_json(text)
    return json.dumps(payload, indent=2) if payload is not None else text


def _parse_verdicts(response: str, *, sentence_count: int) -> tuple[SentenceVerdict, ...] | None:
    """Parses the fact-checker's JSON response into verdicts. Tolerant at
    two levels for two different reasons: a markdown code fence around the
    whole response, or stray text around a JSON object, is stripped before
    parsing (models add these despite being told not to, and stripping them
    costs nothing); but a *malformed individual entry* (a bad `index`, a
    missing `supported`, a duplicate index) is skipped rather than
    invalidating the whole response — one bad entry is not a reason to
    discard every other sentence's real classification, since there is no
    reproduction guarantee at stake here to protect the way the old
    no-reword check did.

    An entry with `"claim": false` (the prompt's explicit way of saying "no
    factual claim here" — user-directed, replacing an earlier
    omit-the-index-entirely convention that gave the model an easy excuse to
    silently drop *any* sentence it found awkward, not just a genuine
    non-claim one) is skipped the same way a missing index used to be: it
    contributes no verdict, so it cannot affect `grounding_score` either
    direction. Only `"claim": false` specifically triggers this — a missing
    `claim` field defaults to treating the entry as a claim, so a response
    from before this field existed still parses.

    The top-level `verified` field, if present, is read by nobody: the
    score is always computed in code from the parsed `results`, never from
    the model's own aggregate self-report."""
    payload = _extract_json(response)
    if not isinstance(payload, dict):
        return None

    results = payload.get("results")
    if not isinstance(results, list):
        return None

    verdicts: dict[int, SentenceVerdict] = {}
    for entry in results:
        if not isinstance(entry, dict):
            continue
        index = entry.get("index")
        if not isinstance(index, int) or isinstance(index, bool) or not (0 <= index < sentence_count):
            continue
        if index in verdicts:
            continue
        if entry.get("claim") is False:
            continue
        supported = entry.get("supported")
        if not isinstance(supported, bool):
            continue
        citations = entry.get("citations")
        citation_ids = tuple(c for c in citations if isinstance(c, str)) if isinstance(citations, list) else ()
        verdicts[index] = SentenceVerdict(index=index, supported=supported, citations=citation_ids)

    return tuple(verdicts.values())


def run_fact_check(
    chat_client: ChatClient, *, evidence: list[Evidence], sentences: tuple[str, ...]
) -> tuple[SentenceVerdict, ...] | None:
    """Renders the fact-check prompt and invokes `chat_client` — the same
    narrow, tool-less `ChatClient` protocol every other generative tool uses
    (ADR-006's boundary applies here too: this call orchestrates nothing and
    reaches no tool). Returns the parsed per-sentence verdicts, or `None` if
    the call itself failed or its response could not be parsed into
    anything usable — the caller (the graph node) treats both the same way:
    fall back to the original, unscored answer.

    Logs the full rendered prompt and the model's response at `INFO`
    (truncated, `core/logging_config.py::truncate`) — mirroring
    `graph/nodes/llm.py::agent_node`'s own `model input`/`model output`
    logging for the primary model, since this call is otherwise a black box:
    the parsed verdicts alone don't show *what the model was actually asked
    to classify*, which is exactly what's needed to diagnose a bad
    `split_sentences` boundary or a malformed response. The response is
    logged pretty-printed (`_pretty`) when it parses as JSON, not as a
    `%r`-escaped single line — the point of this log line is to be read."""
    prompt = render_fact_check_prompt(tuple(evidence), sentences)
    logger.info("fact-check model input:\n%s", truncate(prompt))
    try:
        response = chat_client.invoke(prompt)
    except MythrixError:
        logger.warning("fact-check model call failed")
        return None
    logger.info("fact-check model output:\n%s", truncate(_pretty(response)))
    return _parse_verdicts(response, sentence_count=len(sentences))


def is_grounded(verdict: SentenceVerdict, valid_ids: set[str]) -> bool:
    """Whether `verdict` counts as supported: `supported=True` *and* at
    least one of its citations is actually in `valid_ids`. The boolean alone
    is not trusted, since a claim tagged supported with no real evidence id
    behind it (empty citations, or every id hallucinated) is exactly as
    ungrounded as one tagged unsupported outright. The one rule
    `grounding_score` and the graph node's diagnostic logging both apply, so
    a caller inspecting *why* a score came out low sees the same verdict the
    score itself was computed from."""
    return verdict.supported and any(c in valid_ids for c in verdict.citations)


def grounding_score(verdicts: tuple[SentenceVerdict, ...], valid_ids: set[str]) -> float | None:
    """`supported / (supported + unsupported)`, counted directly from the
    parsed verdicts via `is_grounded` — never self-reported by the model.

    `None` when there are no verdicts at all — nothing was classified as a
    claim, distinct from `0.0`, which specifically means every classified
    claim was unsupported."""
    if not verdicts:
        return None
    supported = sum(1 for v in verdicts if is_grounded(v, valid_ids))
    return supported / len(verdicts)
