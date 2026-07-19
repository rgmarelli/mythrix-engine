"""Citation-marker extraction and validation (FR12) — the code guarantee
behind FR11's "cite every claim" instruction. A prompt can *ask* a model to
only cite real markers; this module is what actually checks it did, by
comparing every `[G#]`/`[S#]` marker found in generated text against the
markers that were genuinely available (via `synthesis/prompts.py`'s
`graph_fact_ids`/`passage_ids` — the same enumerations used to render
context, so validation can't drift from what was shown).

The `query` path itself produces no generated text to validate (FR29) — this
module is retained for the planned conversational agent loop, which will
need exactly this check against its own output. It was originally two
validators matching concept-scoped synthesis's two stages (FR25/FR26);
collapsed to one now that there is only one stage's worth of context to
validate against.
"""

from __future__ import annotations

import re

from mythrix.core.models import GraphFacts, RetrievedPassage
from mythrix.core.synthesis.prompts import graph_fact_ids, passage_ids

_MARKER_PATTERN = re.compile(r"\[(G\d+|S\d+|C\d+)\]")


def extract_markers(text: str) -> tuple[str, ...]:
    """All distinct `[G#]`/`[S#]`/`[C#]` markers in `text`, in first-seen order."""
    return tuple(dict.fromkeys(_MARKER_PATTERN.findall(text)))


def validate_citations(text: str, graph_facts: GraphFacts, passages: tuple[RetrievedPassage, ...]) -> tuple[str, ...]:
    """Returns the markers found in `text` that do *not* correspond to a real
    graph fact or a passage actually present in the given context — empty
    means every citation is valid. `passages` must be exactly the set of
    passages the text was generated from, matching what
    `synthesis/prompts.py`'s `render_passages_block` would render as `[S#]`."""
    valid_ids = set(graph_fact_ids(graph_facts)) | set(passage_ids(passages))
    return tuple(marker for marker in extract_markers(text) if marker not in valid_ids)
