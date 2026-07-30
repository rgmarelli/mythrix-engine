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
    assert [s.locator for s in segments] == ["1. I. The King of the Wood", "2. II. Priestly Kings"]
    assert [s.section for s in segments] == ["", ""]
    assert segments[0].text == "In antiquity this sylvan landscape was the scene of a strange tragedy."


def test_chapter_section_splits_locator_and_section_when_subsections_declared() -> None:
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
    assert segments[0].locator == "1. Diana and Virbius"
    assert segments[0].section == "1. I. The King of the Wood"
    assert segments[1].locator == "2. Artemis and Hippolytus"
    assert segments[1].section == "1. I. The King of the Wood"
    # Chapter II has no subsection match, so it falls back to the implicit
    # whole-chapter subsection: locator carries the chapter, section is empty.
    assert segments[2].locator == "2. II. Priestly Kings"
    assert segments[2].section == ""


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
    assert segments[0].locator == "1. CHAPTER I Introductory"
    assert segments[1].locator == "2. CHAPTER II The Grail"


def test_chapter_section_disambiguates_non_unique_heading_text_by_ordinal() -> None:
    text = (
        "The Ancient Mysteries\n\n"
        "First chapter content.\n\n"
        "The Ancient Mysteries\n\n"
        "Second chapter content, same title as first.\n\n"
    )

    segments = segment_text(text, scheme="chapter_section", chapter_pattern=r"[A-Z][a-zA-Z ]+")

    assert [s.locator for s in segments] == ["1. The Ancient Mysteries", "2. The Ancient Mysteries"]


def test_chapter_section_requires_chapter_pattern() -> None:
    with pytest.raises(MissingChapterPatternError):
        segment_text("I. Title\n\nBody.\n", scheme="chapter_section")


def test_no_segment_overlaps_another() -> None:
    text = "Genesis Chapter 20\n\n20:1. First.\n\n20:2. Second.\n"

    segments = segment_text(text, scheme="scripture_verse")

    for earlier, later in itertools.pairwise(segments):
        assert earlier.char_end <= later.char_start
