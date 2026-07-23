"""Unit tests for `agent/notes.py`."""

from mythrix.agent.notes import split_agent_notes, strip_markdown


def test_splits_visible_reply_from_a_trailing_notes_block() -> None:
    text = "The Tower signifies upheaval.\n\n```agent-notes\nalready summarized this passage\n```"

    visible, notes = split_agent_notes(text)

    assert visible == "The Tower signifies upheaval."
    assert notes == "already summarized this passage"


def test_no_notes_block_returns_the_whole_reply_and_empty_notes() -> None:
    visible, notes = split_agent_notes("Just a plain reply.")
    assert visible == "Just a plain reply."
    assert notes == ""


def test_multiline_notes_block_is_preserved() -> None:
    text = "Reply text.\n```agent-notes\nline one\nline two\n```"

    visible, notes = split_agent_notes(text)

    assert visible == "Reply text."
    assert notes == "line one\nline two"


def test_empty_notes_block_yields_empty_notes() -> None:
    text = "Reply text.\n```agent-notes\n```"

    visible, notes = split_agent_notes(text)

    assert visible == "Reply text."
    assert notes == ""


def test_strip_markdown_removes_bold_and_keeps_the_words() -> None:
    assert strip_markdown("**Genesis 21:5**: Isaac was born.") == "Genesis 21:5: Isaac was born."


def test_strip_markdown_removes_bullet_markers_but_keeps_line_breaks() -> None:
    text = "Here are the segments:\n- Genesis 21:5: Isaac was born.\n- Genesis 21:6: Sara laughed."

    result = strip_markdown(text)

    assert result == "Here are the segments:\nGenesis 21:5: Isaac was born.\nGenesis 21:6: Sara laughed."


def test_strip_markdown_removes_headings() -> None:
    assert strip_markdown("## Summary\nSome text.") == "Summary\nSome text."


def test_strip_markdown_leaves_plain_prose_untouched() -> None:
    assert strip_markdown("Isaac was born when Abraham was a hundred years old.") == (
        "Isaac was born when Abraham was a hundred years old."
    )
