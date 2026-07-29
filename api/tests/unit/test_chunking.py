# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for structure-aware chunking (T12)."""

from mythrix.core.vector.chunking import chunk_text


def test_empty_text_produces_no_chunks() -> None:
    assert chunk_text("") == []


def test_short_text_is_a_single_chunk() -> None:
    text = "A short paragraph that easily fits in one chunk."
    chunks = chunk_text(text, chunk_size=650, chunk_overlap=100)

    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(text)


def test_chunk_boundaries_prefer_paragraph_breaks() -> None:
    paragraph_a = " ".join(f"wordA{i}" for i in range(60))
    paragraph_b = " ".join(f"wordB{i}" for i in range(60))
    text = f"{paragraph_a}\n\n{paragraph_b}"

    chunks = chunk_text(text, chunk_size=60, chunk_overlap=0)

    assert len(chunks) == 2
    assert chunks[0].text == paragraph_a
    assert chunks[1].text == paragraph_b
    # Exact reconstruction from offsets:
    assert text[chunks[0].char_start : chunks[0].char_end] == paragraph_a
    assert text[chunks[1].char_start : chunks[1].char_end] == paragraph_b


def test_oversized_single_paragraph_falls_back_to_word_count_cut() -> None:
    paragraph = " ".join(f"word{i}" for i in range(150))

    chunks = chunk_text(paragraph, chunk_size=100, chunk_overlap=0)

    assert len(chunks) == 2
    assert len(chunks[0].text.split()) == 100
    assert len(chunks[1].text.split()) == 50
    assert chunks[0].char_end == chunks[1].char_start - 1  # separated by one space


def test_overlap_extends_backward_from_previous_chunk() -> None:
    paragraph_a = " ".join(f"wordA{i}" for i in range(60))
    paragraph_b = " ".join(f"wordB{i}" for i in range(60))
    text = f"{paragraph_a}\n\n{paragraph_b}"

    chunks = chunk_text(text, chunk_size=60, chunk_overlap=10)

    assert len(chunks) == 2
    # Second chunk now includes the trailing 10 words of paragraph_a plus all of paragraph_b.
    overlap_words = paragraph_a.split()[-10:]
    assert chunks[1].text.split()[:10] == overlap_words
    assert chunks[1].text.split()[10:] == paragraph_b.split()


def test_chunks_are_indexed_in_order() -> None:
    paragraph_a = " ".join(f"wordA{i}" for i in range(60))
    paragraph_b = " ".join(f"wordB{i}" for i in range(60))
    paragraph_c = " ".join(f"wordC{i}" for i in range(60))
    text = f"{paragraph_a}\n\n{paragraph_b}\n\n{paragraph_c}"

    chunks = chunk_text(text, chunk_size=60, chunk_overlap=0)

    assert [c.index for c in chunks] == [0, 1, 2]


def test_chunks_carry_no_locator_when_the_source_has_no_chapter_headings() -> None:
    text = "A short paragraph that easily fits in one chunk."

    chunks = chunk_text(text, chunk_size=650, chunk_overlap=100)

    assert chunks[0].locator == ""


def test_chunk_locator_is_the_nearest_preceding_chapter_heading() -> None:
    genesis_1 = "Genesis Chapter 1\n\n" + " ".join(f"word{i}" for i in range(60))
    genesis_2 = "Genesis Chapter 2\n\n" + " ".join(f"word{i}" for i in range(60))
    text = f"{genesis_1}\n\n{genesis_2}"

    chunks = chunk_text(text, chunk_size=64, chunk_overlap=0)

    assert [c.locator for c in chunks] == ["Genesis 1", "Genesis 2"]


def test_chunk_locator_handles_numbered_books() -> None:
    text = "1 Corinthians Chapter 5\n\n" + " ".join(f"word{i}" for i in range(30))

    chunks = chunk_text(text, chunk_size=650, chunk_overlap=100)

    assert chunks[0].locator == "1 Corinthians 5"


def test_chunk_locator_is_empty_before_the_first_chapter_heading() -> None:
    preface = " ".join(f"word{i}" for i in range(30))
    genesis_1 = "Genesis Chapter 1\n\n" + " ".join(f"wordB{i}" for i in range(30))
    text = f"{preface}\n\n{genesis_1}"

    chunks = chunk_text(text, chunk_size=30, chunk_overlap=0)

    assert chunks[0].locator == ""
    assert chunks[1].locator == "Genesis 1"
