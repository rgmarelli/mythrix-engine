# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Builds the human-readable `locator` string for a `chapter_section`
segment or region, from the raw structural fields stored on a `Chunk`/
`Segment` (`chapter_ordinal`/`chapter_title`/`subsection_ordinal`/
`subsection_title`) — at query/retrieval time, never at ingest.

This is the single place formatting happens: Title Case (via `titlecase`),
`Ch./§`/`§§` abbreviation, and range-merging for a region spanning several
subsections. Every consumer of a formatted `Segment` — the web UI's region
and reading panels, and the agent/LLM tools (`fetch_segments`, `query_sign`)
— reads the identical already-formatted value, since they all read off
`Segment` objects built through the same handful of construction sites that
call this module.
"""

from __future__ import annotations

import re
from typing import Protocol

from titlecase import titlecase

_NUMBERED_SECTION_LOCATOR = re.compile(r"^§(\d+)$")


class ChapterSectionPoint(Protocol):
    """Anything carrying the four raw `chapter_section` structural fields —
    both `Chunk` and `Segment` satisfy this, so `chapter_section_locator`
    can format either one without importing either concrete type."""

    chapter_ordinal: int
    chapter_title: str
    subsection_ordinal: int
    subsection_title: str


def _number_range(prefix: str, plural_prefix: str, first: int, last: int) -> str:
    return f"{prefix} {first}" if first == last else f"{plural_prefix} {first}–{last}"


def _symbol_range(symbol: str, doubled: str, first: int, last: int) -> str:
    return f"{symbol}{first}" if first == last else f"{doubled}{first}–{last}"


def _title_case(title: str) -> str:
    """`titlecase` treats a line that's *entirely* uppercase as a string of
    intentional acronyms/initials and leaves ordinary words untouched,
    lowercasing only small words (its `all_caps` heuristic) — the opposite
    of what "regardless of source casing" requires here, since a source
    like Primitive Culture's raw ALL-CAPS chapter headings (`"SURVIVAL IN
    CULTURE"`) would otherwise pass through unchanged instead of becoming
    `"Survival in Culture"`. Lowercasing first sidesteps that heuristic
    entirely — `titlecase` then title-cases every word uniformly, which is
    also a no-op for a title that was already correctly mixed-case."""
    return titlecase(title.lower())


def _title_range(first_title: str, last_title: str) -> str:
    first_tc, last_tc = _title_case(first_title), _title_case(last_title)
    return first_tc if first_tc == last_tc else f"{first_tc}–{last_tc}"


def format_chapter_part(first_ordinal: int, first_title: str, last_ordinal: int, last_title: str) -> str:
    """`"Ch. 7: Isis, the Virgin of the World"`, or `"Chs. 6–7: World
    Religions Compared–Isis, the Virgin of the World"` when `first_ordinal`
    and `last_ordinal` differ (a region spanning a chapter boundary)."""
    return f"{_number_range('Ch.', 'Chs.', first_ordinal, last_ordinal)}: {_title_range(first_title, last_title)}"


def format_section_part(first_ordinal: int, first_title: str, last_ordinal: int, last_title: str) -> str:
    """`"§19: The Three Suns"`, or `"§§19–20: The Three Suns–The Celestial
    Inhabitants of the Sun"` when grouping. Bahir-style sections carry no
    title text at all (`numbered_section`, handled separately by
    `merge_numbered_section_locators` — this function only ever sees
    `chapter_section` subsection titles), but the no-title shape is kept
    here too since a `chapter_section` source could in principle declare a
    `subsection_pattern` with no `title` group."""
    number = _symbol_range("§", "§§", first_ordinal, last_ordinal)
    if not first_title and not last_title:
        return number
    return f"{number}: {_title_range(first_title, last_title)}"


def chapter_section_locator(first: ChapterSectionPoint, last: ChapterSectionPoint) -> str:
    """The single formatted `locator` string for a `chapter_section` segment
    or region spanning `first`..`last` — a single point calls this with
    `first=last`. `—` separates the chapter and section parts; this exact
    string is used as-is in both the region panel and the reading-panel
    breadcrumb (`{source} › {locator}`), so there is nothing further for
    either surface to construct."""
    chapter_part = format_chapter_part(
        first.chapter_ordinal, first.chapter_title, last.chapter_ordinal, last.chapter_title
    )
    if first.subsection_title and last.subsection_title:
        section_part = format_section_part(
            first.subsection_ordinal, first.subsection_title, last.subsection_ordinal, last.subsection_title
        )
        return f"{chapter_part} — {section_part}"
    return chapter_part


def merge_numbered_section_locators(first_locator: str, last_locator: str) -> str | None:
    """Merges two already-formatted `numbered_section` locators (e.g. the
    Bahir's `"§83"`/`"§90"`) into a grouped range (`"§§83–90"`), or `None`
    if either doesn't match the plain `"§N"` shape — the caller's signal to
    fall back to its own generic locator join instead."""
    first_match = _NUMBERED_SECTION_LOCATOR.match(first_locator)
    last_match = _NUMBERED_SECTION_LOCATOR.match(last_locator)
    if not first_match or not last_match:
        return None
    return f"§§{first_match.group(1)}–{last_match.group(1)}"
