"""Citation-marker extraction and validation (FR-RT-04) — the code guarantee
behind FR-RT-03's "cite every claim" instruction. A prompt can *ask* a model to
only cite real markers; this module is what actually checks it did, by
comparing every `[G#]`/`[S#]` marker found in generated text against the
markers that were genuinely available (via `synthesis/prompts.py`'s
`graph_fact_ids`/`passage_ids` — the same enumerations used to render
context, so validation can't drift from what was shown).

The `query` path itself produces no generated text to validate (FR-RT-10) —
this module is used by the conversational agent layer (`mythrix.agent`) to
check its own generated output.
"""

from __future__ import annotations

import re

from mythrix.core.models import GraphFacts, RetrievedPassage
from mythrix.core.synthesis.prompts import graph_fact_ids, passage_ids

_MARKER_PATTERN = re.compile(r"\[(G\d+|S\d+|C\d+)\]")


def extract_markers(text: str) -> tuple[str, ...]:
    """All distinct `[G#]`/`[S#]`/`[C#]` markers in `text`, in first-seen order."""
    return tuple(dict.fromkeys(_MARKER_PATTERN.findall(text)))


def strip_markers(text: str) -> str:
    """Removes every `[G#]`/`[S#]`/`[C#]` marker from `text`, valid or not —
    used by the conversational agent, which never shows marker syntax in
    visible replies, regardless of validation outcome."""
    return _MARKER_PATTERN.sub("", text)


def find_invalid_markers(text: str, valid_ids: set[str]) -> tuple[str, ...]:
    """Returns the markers found in `text` that are not present in
    `valid_ids` — empty means every citation is valid. Extracted from
    `validate_citations` so a caller with its own `valid_ids` (e.g. the
    conversational agent, which validates against tool-result dicts rather
    than typed `GraphFacts`/`RetrievedPassage` objects) can reuse the same
    check without constructing those types."""
    return tuple(marker for marker in extract_markers(text) if marker not in valid_ids)


def validate_citations(text: str, graph_facts: GraphFacts, passages: tuple[RetrievedPassage, ...]) -> tuple[str, ...]:
    """Returns the markers found in `text` that do *not* correspond to a real
    graph fact or a passage actually present in the given context — empty
    means every citation is valid. `passages` must be exactly the set of
    passages the text was generated from, matching what
    `synthesis/prompts.py`'s `render_passages_block` would render as `[S#]`."""
    valid_ids = set(graph_fact_ids(graph_facts)) | set(passage_ids(passages))
    return find_invalid_markers(text, valid_ids)
