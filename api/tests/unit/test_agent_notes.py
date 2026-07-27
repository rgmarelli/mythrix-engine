"""Unit tests for `agent/notes.py`."""

from mythrix.agent.notes import strip_markdown


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
