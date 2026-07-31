# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for structural segmentation (T2)."""

import itertools

import pytest

from mythrix.core.vector.segmentation import (
    MissingChapterPatternError,
    UnknownSegmentationSchemeError,
    segment_text,
)


def test_scripture_verse_segments_by_verse_with_stripped_prefix() -> None:
    text = (
        "Genesis Chapter 20\n\n"
        "Abraham sojourned in Gerara.\n\n"
        "20:1. Abraham removed from thence to the south country, and dwelt\n"
        "between Cades and Sur.\n\n"
        "20:2. And he said of Sara his wife: She is my sister.\n\n"
        "Genesis Chapter 21\n\n"
        "Isaac is born.\n\n"
        "21:1. And the Lord visited Sara, as he had promised: and fulfilled what\n"
        "he had spoken.\n"
    )

    segments = segment_text(text, scheme="scripture_verse")

    assert [s.locator for s in segments] == ["Genesis 20:1", "Genesis 20:2", "Genesis 21:1"]
    assert "20:1." not in segments[0].text
    assert segments[0].text.startswith("Abraham removed")
    assert segments[2].text.startswith("And the Lord visited")


def test_scripture_verse_ordinals_are_contiguous_across_chapters() -> None:
    text = (
        "Genesis Chapter 20\n\n20:1. First verse.\n\n20:2. Second verse.\n\nGenesis Chapter 21\n\n21:1. Third verse.\n"
    )

    segments = segment_text(text, scheme="scripture_verse")

    assert [s.ordinal for s in segments] == [0, 1, 2]
    assert [s.section for s in segments] == ["Genesis 20", "Genesis 20", "Genesis 21"]


def test_scripture_verse_skips_non_verse_paragraphs() -> None:
    text = "Genesis Chapter 20\n\nAbraham sojourned in Gerara.\n\n20:1. Abraham removed.\n"

    segments = segment_text(text, scheme="scripture_verse")

    assert len(segments) == 1
    assert segments[0].locator == "Genesis 20:1"


def test_numbered_section_segments_with_stripped_prefix() -> None:
    text = "Title Block\n\n1. First section text.\n\n2. Second section text.\n\n83. And what is Nun?\n"

    segments = segment_text(text, scheme="numbered_section")

    assert [s.locator for s in segments] == ["§1", "§2", "§83"]
    assert [s.ordinal for s in segments] == [0, 1, 2]
    assert "83." not in segments[2].text
    assert segments[2].text == "And what is Nun?"


def test_numbered_section_skips_the_title_block() -> None:
    text = "Sefer HaBahir\nThe Book of Brightness\n\n1. Rabbi Nechunia ben Hakana said..."

    segments = segment_text(text, scheme="numbered_section")

    assert len(segments) == 1
    assert segments[0].section == ""


def test_paragraph_scheme_segments_every_paragraph_verbatim() -> None:
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."

    segments = segment_text(text, scheme="paragraph")

    assert [s.text for s in segments] == ["First paragraph.", "Second paragraph.", "Third paragraph."]
    assert [s.ordinal for s in segments] == [0, 1, 2]


def test_unknown_scheme_raises() -> None:
    with pytest.raises(UnknownSegmentationSchemeError):
        segment_text("some text", scheme="not_a_real_scheme")


def test_chapter_section_groups_paragraphs_by_chapter_and_excludes_front_matter() -> None:
    text = (
        "PREFACE\n\n"
        "This is the preface text, not part of any chapter.\n\n"
        "I. The King of the Wood\n\n"
        "In antiquity this sylvan landscape was the scene of a strange tragedy.\n\n"
        "II. Priestly Kings\n\n"
        "The rule which the priest guarded was itself only a special case.\n\n"
    )

    segments = segment_text(text, scheme="chapter_section", chapter_pattern=r"[IVX]+\. [A-Z].+")

    assert len(segments) == 2
    # No `(?P<title>...)` group in this pattern, so chapter_title falls back
    # to the paragraph's own full matched text — same text `locator` used to
    # store directly, before formatting moved to query time.
    assert [s.locator for s in segments] == ["", ""]
    assert [s.chapter_ordinal for s in segments] == [1, 2]
    assert [s.chapter_title for s in segments] == ["I. The King of the Wood", "II. Priestly Kings"]
    assert [s.subsection_title for s in segments] == ["", ""]
    assert [s.section for s in segments] == ["1. I. The King of the Wood", "2. II. Priestly Kings"]
    assert segments[0].text == "In antiquity this sylvan landscape was the scene of a strange tragedy."


def test_chapter_section_splits_chapter_and_subsection_into_structured_fields() -> None:
    text = (
        "I. The King of the Wood\n\n"
        "1. Diana and Virbius\n\n"
        "Diana was worshipped in various ways.\n\n"
        "2. Artemis and Hippolytus\n\n"
        "Artemis parallels exist in Greek myth.\n\n"
        "II. Priestly Kings\n\n"
        "This chapter has no subsections at all.\n\n"
    )

    segments = segment_text(
        text,
        scheme="chapter_section",
        chapter_pattern=r"[IVX]+\. [A-Z].+",
        subsection_pattern=r"\d+\. [A-Z].+",
    )

    assert len(segments) == 3
    assert [s.locator for s in segments] == ["", "", ""]

    assert segments[0].chapter_ordinal == 1
    assert segments[0].chapter_title == "I. The King of the Wood"
    assert segments[0].subsection_ordinal == 1
    assert segments[0].subsection_title == "1. Diana and Virbius"
    assert segments[0].section == "1. I. The King of the Wood"

    assert segments[1].chapter_ordinal == 1
    assert segments[1].chapter_title == "I. The King of the Wood"
    assert segments[1].subsection_ordinal == 2
    assert segments[1].subsection_title == "2. Artemis and Hippolytus"
    assert segments[1].section == "1. I. The King of the Wood"

    # Chapter II has no subsection match, so subsection fields stay at the
    # reset value a new chapter starts with; section still carries the
    # disambiguated chapter key.
    assert segments[2].chapter_ordinal == 2
    assert segments[2].chapter_title == "II. Priestly Kings"
    assert segments[2].subsection_ordinal == 0
    assert segments[2].subsection_title == ""
    assert segments[2].section == "2. II. Priestly Kings"


def test_chapter_section_subsection_ordinal_is_global_not_per_chapter() -> None:
    """A subsection's displayed number must keep counting across a chapter
    boundary, not restart at 1 — even when the source's own subsection
    marker (unused for the displayed number; see module docstring) happens
    to restart per chapter, as Secret Teachings' SECTION markers do not,
    but a differently-structured source might."""
    text = (
        "I. Chapter One\n\n"
        "1. First Subsection\n\n"
        "First subsection body.\n\n"
        "2. Second Subsection\n\n"
        "Second subsection body.\n\n"
        "II. Chapter Two\n\n"
        "1. Restarts In The Source Itself\n\n"
        "Third subsection body, but the third one seen overall.\n\n"
    )

    segments = segment_text(
        text,
        scheme="chapter_section",
        chapter_pattern=r"[IVX]+\. [A-Z].+",
        subsection_pattern=r"\d+\. [A-Z].+",
    )

    assert len(segments) == 3
    assert [s.subsection_ordinal for s in segments] == [1, 2, 3]


def test_chapter_section_extracts_title_from_named_capture_group() -> None:
    text = (
        "CHAPTER 9.\nThe Zodiac and Its Signs\n\n"
        "SECTION 19.\nTHE THREE SUNS\n\n"
        "There are three suns spoken of by the ancients.\n\n"
    )

    segments = segment_text(
        text,
        scheme="chapter_section",
        chapter_pattern=r"CHAPTER \d+\.\n(?P<title>.+)",
        subsection_pattern=r"SECTION \d+\.\n(?P<title>.+)",
    )

    assert len(segments) == 1
    # The displayed ordinal is a running counter, not the source's own
    # "CHAPTER 9"/"SECTION 19" number (see module docstring) — this text
    # has only one chapter and one subsection, so both count from 1.
    assert segments[0].chapter_ordinal == 1
    assert segments[0].chapter_title == "The Zodiac and Its Signs"
    assert segments[0].subsection_ordinal == 1
    assert segments[0].subsection_title == "THE THREE SUNS"
    assert segments[0].locator == ""


def test_chapter_section_title_cleanup_strips_trailing_period_and_gutenberg_italics() -> None:
    text = "CHAPTER IX.\nMythology _(continued)_.\n\nBody paragraph text here.\n\n"

    segments = segment_text(
        text,
        scheme="chapter_section",
        chapter_pattern=r"CHAPTER [IVXLC]+\.\n(?P<title>.+)",
    )

    assert segments[0].chapter_title == "Mythology (continued)"
    # Cleanup is scoped to the title field alone — body text is untouched.
    assert segments[0].text == "Body paragraph text here."


def test_chapter_section_occurrence_bounds_exclude_table_of_contents_and_endnotes() -> None:
    # Mirrors From Ritual to Romance's real shape: the same heading text
    # repeats as a table-of-contents entry, then a real chapter, then an
    # endnotes-section header.
    text = (
        "CHAPTER I\nIntroductory\n\n"  # ToC entry (match 1)
        "CHAPTER II\nThe Grail\n\n"  # ToC entry (match 2)
        "CHAPTER I\nIntroductory\n\n"  # real chapter 1 (match 3)
        "Real chapter one content here.\n\n"
        "CHAPTER II\nThe Grail\n\n"  # real chapter 2 (match 4)
        "Real chapter two content here.\n\n"
        "CHAPTER II\nThe Grail\n\n"  # endnotes header (match 5)
        "Endnote citation text should be excluded.\n\n"
    )

    segments = segment_text(
        text,
        scheme="chapter_section",
        chapter_pattern=r"CHAPTER [IVX]+\n[A-Z].+",
        body_start_occurrence=3,
        body_end_occurrence=4,
    )

    assert [s.text for s in segments] == ["Real chapter one content here.", "Real chapter two content here."]
    assert segments[0].chapter_title == "CHAPTER I Introductory"
    assert segments[1].chapter_title == "CHAPTER II The Grail"
    assert segments[0].locator == ""


def test_chapter_section_disambiguates_repeated_heading_text_by_section_not_chapter_title() -> None:
    # A source can genuinely reuse one chapter title (e.g. The Secret
    # Teachings of All Ages' two "Fishes, Insects, Animals..." chapters).
    # `chapter_title` shows that repeat plainly since it's just for display,
    # but `section` must stay distinct — it's what extend_context compares
    # to stop growth at a chapter boundary.
    text = (
        "The Ancient Mysteries\n\n"
        "First chapter content.\n\n"
        "The Ancient Mysteries\n\n"
        "Second chapter content, same title as first.\n\n"
    )

    segments = segment_text(text, scheme="chapter_section", chapter_pattern=r"[A-Z][a-zA-Z ]+")

    assert [s.chapter_title for s in segments] == ["The Ancient Mysteries", "The Ancient Mysteries"]
    assert [s.section for s in segments] == ["1. The Ancient Mysteries", "2. The Ancient Mysteries"]


def test_chapter_section_requires_chapter_pattern() -> None:
    with pytest.raises(MissingChapterPatternError):
        segment_text("I. Title\n\nBody.\n", scheme="chapter_section")


def test_no_segment_overlaps_another() -> None:
    text = "Genesis Chapter 20\n\n20:1. First.\n\n20:2. Second.\n"

    segments = segment_text(text, scheme="scripture_verse")

    for earlier, later in itertools.pairwise(segments):
        assert earlier.char_end <= later.char_start
