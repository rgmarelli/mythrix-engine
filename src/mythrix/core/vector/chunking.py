"""Structure-aware chunking for source documents ingested into the vector store
(plan.md "Chroma vector store design").

Chunk size/overlap are measured in whitespace-delimited words, used as a
lightweight, dependency-free proxy for LLM tokens (no tokenizer package is
pinned in `pyproject.toml`) — close enough for the target ranges plan.md
describes (~500-800 tokens, ~100 overlap) without adding a dependency whose
only job is counting.

Paragraph boundaries are preferred over a plain word-count cut, since naive
fixed-size chunking risks severing a claim from its supporting context in
list-like correspondence text (e.g. "Element: Fire"). A paragraph longer than
`chunk_size` on its own falls back to a plain word-count cut, since it has no
finer structure to split on.

Each chunk also gets a best-effort `locator` (e.g. "Genesis 21") — the most
recent "<Title> Chapter <N>"-style heading found in the source text before
the chunk's own start. This is a generic structural heuristic, not specific
to any one source's content (a document using this heading convention gets
locators; one that doesn't just gets an empty string per chunk, same as
before this existed) — found useful because a researcher reading a verbatim
Bible passage in the CLI's References section had no way to tell which
chapter it came from otherwise.
"""

from __future__ import annotations

import bisect
import re

from pydantic import BaseModel, ConfigDict

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n+")
_WORD = re.compile(r"\S+")
_CHAPTER_HEADING = re.compile(r"^(?:[0-9] )?[A-Za-z][A-Za-z ]* Chapter [0-9]+$", re.MULTILINE)


class Chunk(BaseModel):
    """One chunk of a source document, carrying its exact span in the original
    text (`char_start`/`char_end`) so a citation can point back to it precisely,
    plus a best-effort chapter-style `locator` (see module docstring)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    text: str
    char_start: int
    char_end: int
    locator: str = ""
    ordinal: int = 0
    section: str = ""


def chunk_text(text: str, *, chunk_size: int = 650, chunk_overlap: int = 100) -> list[Chunk]:
    """Splits `text` into overlapping chunks, preferring paragraph boundaries."""
    words = [(m.start(), m.end()) for m in _WORD.finditer(text)]
    if not words:
        return []

    paragraph_ranges = _paragraph_word_ranges(text, words)
    windows = _paragraph_aware_windows(paragraph_ranges, chunk_size)
    windows = _apply_overlap(windows, chunk_overlap)
    headings = _chapter_headings(text)

    chunks = []
    for index, (start_idx, end_idx) in enumerate(windows):
        char_start = words[start_idx][0]
        char_end = words[end_idx - 1][1]
        chunks.append(
            Chunk(
                index=index,
                text=text[char_start:char_end],
                char_start=char_start,
                char_end=char_end,
                locator=_locator_at(char_start, headings),
                ordinal=index,
            )
        )
    return chunks


def _chapter_headings(text: str) -> list[tuple[int, str]]:
    """Every chapter-style heading in `text` (e.g. "Genesis Chapter 21"), as
    `(char_position, locator)` pairs sorted by position — `locator` drops the
    word "Chapter" for a citation-style reference (e.g. "Genesis 21")."""
    return [(m.start(), m.group(0).replace(" Chapter ", " ")) for m in _CHAPTER_HEADING.finditer(text)]


def _locator_at(char_start: int, headings: list[tuple[int, str]]) -> str:
    """The most recent heading at or before `char_start`, or `""` if none —
    `headings` is already position-sorted since regex matches are found in
    order, so a binary search finds it in O(log n)."""
    idx = bisect.bisect_right([pos for pos, _ in headings], char_start) - 1
    return headings[idx][1] if idx >= 0 else ""


def _paragraph_word_ranges(text: str, words: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Returns `(start_word_idx, end_word_idx_exclusive)` for each paragraph,
    derived from blank-line breaks in `text`."""
    word_starts = [start for start, _ in words]
    break_ends = sorted(m.end() for m in _PARAGRAPH_BREAK.finditer(text))

    para_starts = {0}
    for pos in break_ends:
        idx = _first_word_at_or_after(word_starts, pos)
        if idx < len(words):
            para_starts.add(idx)

    ordered_starts = sorted(para_starts)
    ranges = []
    for i, start in enumerate(ordered_starts):
        end = ordered_starts[i + 1] if i + 1 < len(ordered_starts) else len(words)
        if end > start:
            ranges.append((start, end))
    return ranges


def _first_word_at_or_after(word_starts: list[int], char_pos: int) -> int:
    return bisect.bisect_left(word_starts, char_pos)


def _paragraph_aware_windows(paragraph_ranges: list[tuple[int, int]], chunk_size: int) -> list[tuple[int, int]]:
    """Greedily accumulates whole paragraphs into a window up to `chunk_size`
    words; a paragraph longer than `chunk_size` on its own is hard-sliced by
    word count (the "recursive splitter fallback" from plan.md, simplified to
    a flat word-count cut since a single paragraph has no further structure)."""
    windows: list[tuple[int, int]] = []
    current: tuple[int, int] | None = None

    for para_start, para_end in paragraph_ranges:
        para_len = para_end - para_start
        if para_len > chunk_size:
            if current is not None:
                windows.append(current)
                current = None
            pos = para_start
            while pos < para_end:
                end = min(pos + chunk_size, para_end)
                windows.append((pos, end))
                pos = end
            continue

        if current is None:
            current = (para_start, para_end)
        elif (current[1] - current[0]) + para_len <= chunk_size:
            current = (current[0], para_end)
        else:
            windows.append(current)
            current = (para_start, para_end)

    if current is not None:
        windows.append(current)
    return windows


def _apply_overlap(windows: list[tuple[int, int]], chunk_overlap: int) -> list[tuple[int, int]]:
    """Extends each window (after the first) backward by up to `chunk_overlap`
    words, clamped so it never reaches earlier than the previous window's own
    (possibly already-overlapped) start — this bounds duplication instead of
    letting it compound across many chunks."""
    overlapped = []
    previous_start = 0
    for i, (start, end) in enumerate(windows):
        if i > 0:
            start = max(previous_start, start - chunk_overlap)
        overlapped.append((start, end))
        previous_start = start
    return overlapped
