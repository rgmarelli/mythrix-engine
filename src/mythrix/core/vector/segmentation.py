"""Structural segmenters (plan.md area A, `convergence-rollup-retrieval` FR1-FR2).

Each scheme below turns a source's raw text into one `Chunk` (segment) per
smallest structural unit the source itself declares (a scripture verse, a
numbered section), rather than a fixed word-count window. A segment never
spans a paragraph break, so it never spans the structural boundary that break
represents, and no segment overlaps another. The structural-label prefix
(e.g. a leading verse or section number) is excluded from the segment's own
`text` so it neither influences embedding nor produces spurious token
containment (FR2).
"""

from __future__ import annotations

import re

from mythrix.core.vector.chunking import _PARAGRAPH_BREAK, Chunk, _chapter_headings, _locator_at, normalize_chunk_text

_VERSE_MARKER = re.compile(r"^(\d+):(\d+)\.\s+")
_SECTION_MARKER = re.compile(r"^(\d+)\.\s+")


class UnknownSegmentationSchemeError(ValueError):
    """Raised for a `structure.scheme` value no segmenter recognizes."""


def segment_text(text: str, *, scheme: str) -> list[Chunk]:
    """Dispatches to the named structural segmenter. Raises
    `UnknownSegmentationSchemeError` for an unrecognized `scheme`."""
    if scheme == "scripture_verse":
        return _segment_scripture_verse(text)
    if scheme == "numbered_section":
        return _segment_numbered_section(text)
    if scheme == "paragraph":
        return _segment_paragraph(text)
    raise UnknownSegmentationSchemeError(f"Unknown segmentation scheme: {scheme!r}")


def _paragraphs(text: str) -> list[tuple[int, int]]:
    """`(char_start, char_end)` for each non-blank paragraph in `text`,
    trimmed of surrounding whitespace, in document order — the char-range
    analogue of `chunking._paragraph_word_ranges`, needed here because a
    segment's span must be exact character positions, not word indices."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for match in _PARAGRAPH_BREAK.finditer(text):
        _append_paragraph_span(spans, text, pos, match.start())
        pos = match.end()
    _append_paragraph_span(spans, text, pos, len(text))
    return spans


def _append_paragraph_span(spans: list[tuple[int, int]], text: str, start: int, end: int) -> None:
    raw = text[start:end]
    stripped = raw.strip()
    if not stripped:
        return
    offset = raw.find(stripped)
    spans.append((start + offset, start + offset + len(stripped)))


def _segment_scripture_verse(text: str) -> list[Chunk]:
    """One segment per verse (e.g. `"20:1. Abraham removed..."`). The
    enclosing chapter's heading (e.g. `"Genesis Chapter 20"`, already reduced
    to `"Genesis 20"` by `_chapter_headings`) supplies the book name; `section`
    carries that chapter locator so a consumer can group segments by chapter
    without re-deriving it, though contiguity itself is ordinal-based (FR2),
    not section-based. A paragraph with no leading `chapter:verse.` marker
    (chapter summaries, the book preface) is not a verse and is skipped."""
    headings = _chapter_headings(text)
    chunks: list[Chunk] = []
    ordinal = 0
    for start, end in _paragraphs(text):
        paragraph = text[start:end]
        match = _VERSE_MARKER.match(paragraph)
        if not match:
            continue
        chapter_locator = _locator_at(start, headings)
        book, _, _ = chapter_locator.rpartition(" ")
        chapter, verse = match.group(1), match.group(2)
        locator = f"{book} {chapter}:{verse}" if book else f"{chapter}:{verse}"
        body_start = start + match.end()
        chunks.append(
            Chunk(
                index=ordinal,
                text=normalize_chunk_text(paragraph[match.end() :]),
                char_start=body_start,
                char_end=end,
                locator=locator,
                ordinal=ordinal,
                section=chapter_locator,
            )
        )
        ordinal += 1
    return chunks


def _segment_numbered_section(text: str) -> list[Chunk]:
    """One segment per numbered section (e.g. `"83. And what is Nun?..."`,
    the Bahir's own structure). A paragraph with no leading `N.` marker (the
    title block, translator's note) is not a section and is skipped."""
    chunks: list[Chunk] = []
    ordinal = 0
    for start, end in _paragraphs(text):
        paragraph = text[start:end]
        match = _SECTION_MARKER.match(paragraph)
        if not match:
            continue
        section = match.group(1)
        body_start = start + match.end()
        chunks.append(
            Chunk(
                index=ordinal,
                text=normalize_chunk_text(paragraph[match.end() :]),
                char_start=body_start,
                char_end=end,
                locator=f"§{section}",
                ordinal=ordinal,
                section=section,
            )
        )
        ordinal += 1
    return chunks


def _segment_paragraph(text: str) -> list[Chunk]:
    """One segment per paragraph, verbatim — for a source declaring no finer
    structure than paragraph breaks. No prefix to strip and no numbering to
    use as a locator, so `locator`/`section` stay empty."""
    chunks: list[Chunk] = []
    for ordinal, (start, end) in enumerate(_paragraphs(text)):
        chunks.append(
            Chunk(index=ordinal, text=normalize_chunk_text(text[start:end]), char_start=start, char_end=end, ordinal=ordinal)
        )
    return chunks
