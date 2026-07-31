# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `mythrix.core.retrieval.locator_format` — the single
place a `chapter_section` segment/region's display `locator` is built, at
query time, from raw structural fields."""

from dataclasses import dataclass

from mythrix.core.retrieval.locator_format import (
    chapter_section_locator,
    format_chapter_part,
    format_section_part,
    merge_numbered_section_locators,
)


@dataclass
class _Point:
    chapter_ordinal: int
    chapter_title: str
    subsection_ordinal: int = 0
    subsection_title: str = ""


def test_format_chapter_part_single_chapter() -> None:
    assert format_chapter_part(7, "isis, the virgin of the world", 7, "isis, the virgin of the world") == (
        "Ch. 7: Isis, the Virgin of the World"
    )


def test_format_chapter_part_grouped_range_pluralizes() -> None:
    assert format_chapter_part(6, "World Religions Compared", 7, "Isis, the Virgin of the World") == (
        "Chs. 6–7: World Religions Compared–Isis, the Virgin of the World"
    )


def test_format_section_part_single_section() -> None:
    assert format_section_part(19, "THE THREE SUNS", 19, "THE THREE SUNS") == "§19: The Three Suns"


def test_format_section_part_grouped_range() -> None:
    assert format_section_part(19, "THE THREE SUNS", 20, "THE CELESTIAL INHABITANTS OF THE SUN") == (
        "§§19–20: The Three Suns–The Celestial Inhabitants of the Sun"
    )


def test_format_section_part_with_no_title_text_is_bahir_style() -> None:
    assert format_section_part(83, "", 83, "") == "§83"
    assert format_section_part(83, "", 90, "") == "§§83–90"


def test_chapter_section_locator_not_grouping_with_subsection() -> None:
    point = _Point(7, "Isis, the Virgin of the World", 19, "THE THREE SUNS")

    assert chapter_section_locator(point, point) == "Ch. 7: Isis, the Virgin of the World — §19: The Three Suns"


def test_chapter_section_locator_grouping_subsections_within_one_chapter() -> None:
    first = _Point(7, "Isis, the Virgin of the World", 19, "THE THREE SUNS")
    last = _Point(7, "Isis, the Virgin of the World", 20, "THE CELESTIAL INHABITANTS OF THE SUN")

    assert chapter_section_locator(first, last) == (
        "Ch. 7: Isis, the Virgin of the World — §§19–20: The Three Suns–The Celestial Inhabitants of the Sun"
    )


def test_chapter_section_locator_grouping_across_chapters() -> None:
    first = _Point(6, "World Religions Compared")
    last = _Point(7, "Isis, the Virgin of the World")

    assert chapter_section_locator(first, last) == "Chs. 6–7: World Religions Compared–Isis, the Virgin of the World"


def test_chapter_section_locator_with_no_subsection_layer() -> None:
    point = _Point(2, "Homoeopathic or Imitative Magic")

    assert chapter_section_locator(point, point) == "Ch. 2: Homoeopathic or Imitative Magic"


def test_chapter_section_locator_title_cases_an_all_caps_source_title() -> None:
    """`titlecase` treats a fully-uppercase line as intentional acronyms and
    leaves it untouched by default (its `all_caps` heuristic) — a source
    like Primitive Culture, whose raw chapter headings are ALL CAPS
    (`"SURVIVAL IN CULTURE (Continued)"`), must still come out properly
    Title-Cased, not pass through unchanged."""
    point = _Point(4, "SURVIVAL IN CULTURE (Continued)")

    assert chapter_section_locator(point, point) == "Ch. 4: Survival in Culture (Continued)"


def test_merge_numbered_section_locators_grouped() -> None:
    assert merge_numbered_section_locators("§83", "§90") == "§§83–90"


def test_merge_numbered_section_locators_returns_none_for_non_numbered_section_locators() -> None:
    assert merge_numbered_section_locators("Genesis 21:5", "Genesis 21:6") is None
