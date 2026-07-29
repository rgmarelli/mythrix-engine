"""Unit tests for structural segmentation (T2)."""

import itertools

import pytest

from mythrix.core.vector.segmentation import UnknownSegmentationSchemeError, segment_text


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


def test_no_segment_overlaps_another() -> None:
    text = "Genesis Chapter 20\n\n20:1. First.\n\n20:2. Second.\n"

    segments = segment_text(text, scheme="scripture_verse")

    for earlier, later in itertools.pairwise(segments):
        assert earlier.char_end <= later.char_start
