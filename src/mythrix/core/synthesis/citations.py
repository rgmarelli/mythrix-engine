"""Citation-marker extraction and validation (FR12) — the code guarantee behind
FR11's "cite every claim" instruction. A prompt can *ask* the model to only
cite real markers; this module is what actually checks it did, by comparing
every `[G#]`/`[S#]` marker found in the output against the markers that were
genuinely available in the supplied `RetrievalContext` (via
`synthesis/prompts.py`'s `graph_fact_ids`/`passage_ids` — the same enumeration
used to render the prompt, so validation can't drift from what was shown).
"""

from __future__ import annotations

import re

from mythrix.core.models import RetrievalContext
from mythrix.core.synthesis.prompts import graph_fact_ids, passage_ids

_MARKER_PATTERN = re.compile(r"\[(G\d+|S\d+)\]")


def extract_markers(text: str) -> tuple[str, ...]:
    """All distinct `[G#]`/`[S#]` markers in `text`, in first-seen order."""
    return tuple(dict.fromkeys(_MARKER_PATTERN.findall(text)))


def validate_citations(text: str, context: RetrievalContext) -> tuple[str, ...]:
    """Returns the markers found in `text` that do *not* correspond to a real
    graph fact or passage in `context` — empty means every citation is valid."""
    valid_ids = set(graph_fact_ids(context.graph_facts)) | set(passage_ids(context.passages))
    return tuple(marker for marker in extract_markers(text) if marker not in valid_ids)
