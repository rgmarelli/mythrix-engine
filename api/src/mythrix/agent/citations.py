"""Citation-marker extraction over the `[G#]`/`[S#]`/`[C#]` vocabulary
`prompts.py`'s `SYSTEM_PROMPT` instructs the model to use — the code guarantee
(FR-RT-04) behind that instruction. A prompt can *ask* a model to cite only
real markers; this is what checks it did.

Deliberately typeless: it works on text and a set of valid identifiers, never
on retrieval or graph models, so `turn_service.py` can validate against the
markers it enumerated from its own tool results. The `query` path produces no
generated text to validate (FR-RT-10).
"""

from __future__ import annotations

import re

_MARKER_PATTERN = re.compile(r"\[(G\d+|S\d+|C\d+)\]")


def extract_markers(text: str) -> tuple[str, ...]:
    """All distinct `[G#]`/`[S#]`/`[C#]` markers in `text`, in first-seen order."""
    return tuple(dict.fromkeys(_MARKER_PATTERN.findall(text)))


def strip_markers(text: str) -> str:
    """Removes every `[G#]`/`[S#]`/`[C#]` marker from `text`, valid or not —
    the agent never shows marker syntax in visible replies, regardless of
    validation outcome."""
    return _MARKER_PATTERN.sub("", text)


def find_invalid_markers(text: str, valid_ids: set[str]) -> tuple[str, ...]:
    """The markers found in `text` that are not present in `valid_ids` — empty
    means every citation is valid."""
    return tuple(marker for marker in extract_markers(text) if marker not in valid_ids)
