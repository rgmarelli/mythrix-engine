"""Citation-marker extraction over the `[G#]`/`[S#]`/`[C#]`/`[R#]` vocabulary —
the code guarantee (FR-RT-04) behind the instruction to use it. A prompt can
*ask* a model to cite only real markers; this is what checks it did.

Validation and stripping are separate predicates. Every marker kind is
validated against the caller's identifier set; only the kinds that name an item
*inside* a tool result are then removed from the visible reply. A region marker
names a section of the reply itself, so it is kept — it is what lets a
consolidated claim be traced to the finding supporting it (FR-DS-23).

Deliberately typeless: it works on text and a set of valid identifiers, never
on retrieval or graph models, so `turn_service.py` can validate against the
markers it enumerated from its own tool results. The `query` path produces no
generated text to validate (FR-RT-10).
"""

from __future__ import annotations

import re

_MARKER_PATTERN = re.compile(r"\[(G\d+|S\d+|C\d+|R\d+)\]")
_STRIP_PATTERN = re.compile(r"\[(G\d+|S\d+|C\d+)\]")


def extract_markers(text: str) -> tuple[str, ...]:
    """All distinct citation markers in `text`, in first-seen order."""
    return tuple(dict.fromkeys(_MARKER_PATTERN.findall(text)))


def strip_markers(text: str) -> str:
    """Removes every `[G#]`/`[S#]`/`[C#]` marker from `text`, valid or not —
    the agent never shows those in a visible reply, regardless of validation
    outcome. Region markers survive (FR-DS-23)."""
    return _STRIP_PATTERN.sub("", text)


def strip_all_markers(text: str) -> str:
    """Removes every marker of every kind from `text`.

    For generated text that is composed *into* a larger reply rather than
    being one: a marker there was emitted against a vocabulary the call was
    never given, so it cites nothing, and leaving it in would put a marker the
    backend does not control in front of validation (FR-DS-25)."""
    return _MARKER_PATTERN.sub("", text)


def find_invalid_markers(text: str, valid_ids: set[str]) -> tuple[str, ...]:
    """The markers found in `text` that are not present in `valid_ids` — empty
    means every citation is valid."""
    return tuple(marker for marker in extract_markers(text) if marker not in valid_ids)
