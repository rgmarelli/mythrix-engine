# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Structural segmenters (FR-CO-05–FR-CO-06).

Each scheme below turns a source's raw text into one `Chunk` (segment) per
smallest structural unit the source itself declares (a scripture verse, a
numbered section), rather than a fixed word-count window. A segment never
spans a paragraph break, so it never spans the structural boundary that break
represents, and no segment overlaps another. The structural-label prefix
(e.g. a leading verse or section number) is excluded from the segment's own
`text` so it neither influences embedding nor produces spurious token
containment (FR-CO-06).
"""

from __future__ import annotations

import re

from mythrix.core.vector.chunking import _PARAGRAPH_BREAK, Chunk, _chapter_headings, _locator_at, normalize_chunk_text

_VERSE_MARKER = re.compile(r"^(\d+):(\d+)\.\s+")
_SECTION_MARKER = re.compile(r"^(\d+)\.\s+")


class UnknownSegmentationSchemeError(ValueError):
    """Raised for a `structure.scheme` value no segmenter recognizes."""


class MissingChapterPatternError(ValueError):
    """Raised when a `chapter_section` source declares no `chapter_pattern`
    (FR-CO-09) — the one field the scheme cannot function without."""


def segment_text(
    text: str,
    *,
    scheme: str,
    chapter_pattern: str | None = None,
    subsection_pattern: str | None = None,
    body_start_occurrence: int = 1,
    body_end_occurrence: int = 0,
) -> list[Chunk]:
    """Dispatches to the named structural segmenter. Raises
    `UnknownSegmentationSchemeError` for an unrecognized `scheme`.

    `chapter_pattern`/`subsection_pattern`/`body_start_occurrence`/
    `body_end_occurrence` configure `chapter_section` only (FR-CO-08–FR-CO-12)
    — every other scheme ignores them."""
    if scheme == "scripture_verse":
        return _segment_scripture_verse(text)
    if scheme == "numbered_section":
        return _segment_numbered_section(text)
    if scheme == "paragraph":
        return _segment_paragraph(text)
    if scheme == "chapter_section":
        return _segment_chapter_section(
            text,
            chapter_pattern=chapter_pattern,
            subsection_pattern=subsection_pattern,
            body_start_occurrence=body_start_occurrence,
            body_end_occurrence=body_end_occurrence,
        )
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
    without re-deriving it, though contiguity itself is ordinal-based (FR-CO-06),
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
    title block, translator's note) is not a section and is skipped. A
    numbered section has no grouping above itself, so like `_segment_paragraph`,
    `section` stays empty; `locator` alone carries the section number."""
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
            Chunk(
                index=ordinal,
                text=normalize_chunk_text(text[start:end]),
                char_start=start,
                char_end=end,
                ordinal=ordinal,
            )
        )
    return chunks


def _segment_chapter_section(
    text: str,
    *,
    chapter_pattern: str | None,
    subsection_pattern: str | None,
    body_start_occurrence: int,
    body_end_occurrence: int,
) -> list[Chunk]:
    """One segment per paragraph within a source whose only declared
    structure is chapter headings, optionally with a finer subsection layer
    (FR-CO-08–FR-CO-12) — for chaptered prose with no per-paragraph
    numbering (e.g. *The Golden Bough*). A heading is a paragraph whose
    *entire* text fullmatches `chapter_pattern`/`subsection_pattern`, not a
    substring found anywhere, so a source's own table of contents or
    endnotes section reusing the same heading text does not collide with
    its real chapters as long as the pattern itself, or
    `body_start_occurrence`/`body_end_occurrence`, excludes it. A
    chapter-heading match outside `[body_start_occurrence,
    body_end_occurrence or unbounded]` (a table-of-contents or endnotes
    repeat) starts an excluded region: paragraphs are skipped until the
    next in-range chapter-heading match, if any.

    `locator`/`section` follow `_segment_scripture_verse`'s split: the
    finest declared level is `locator`, the coarser one (if any) is
    `section`. A source with no `subsection_pattern`, or a chapter with no
    subsection match yet, has only the chapter level — `locator` carries the
    chapter label and `section` stays empty, the same "no grouping above
    itself" treatment `_segment_numbered_section` gives a bare section. A
    chapter label always includes a running ordinal, not just the heading's
    own text, since heading text is not guaranteed unique within a source
    (e.g. *The Secret Teachings of All Ages* repeats one chapter title
    across three distinct chapters)."""
    if not chapter_pattern:
        raise MissingChapterPatternError("chapter_section requires a non-empty chapter_pattern.")

    chapter_re = re.compile(chapter_pattern)
    subsection_re = re.compile(subsection_pattern) if subsection_pattern else None
    upper_bound = body_end_occurrence if body_end_occurrence > 0 else None

    chunks: list[Chunk] = []
    ordinal = 0
    match_count = 0
    in_body = False
    chapter_ordinal = 0
    chapter_label = ""
    subsection_label = ""

    for start, end in _paragraphs(text):
        paragraph = text[start:end]

        if chapter_re.fullmatch(paragraph):
            match_count += 1
            in_body = match_count >= body_start_occurrence and (upper_bound is None or match_count <= upper_bound)
            if in_body:
                chapter_ordinal += 1
                chapter_label = f"{chapter_ordinal}. {normalize_chunk_text(paragraph)}"
                subsection_label = ""
            continue

        if not in_body:
            continue

        if subsection_re is not None and subsection_re.fullmatch(paragraph):
            subsection_label = normalize_chunk_text(paragraph)
            continue

        locator, section = (subsection_label, chapter_label) if subsection_label else (chapter_label, "")
        chunks.append(
            Chunk(
                index=ordinal,
                text=normalize_chunk_text(paragraph),
                char_start=start,
                char_end=end,
                locator=locator,
                ordinal=ordinal,
                section=section,
            )
        )
        ordinal += 1

    return chunks
