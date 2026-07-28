"""Unit tests for `agent/prompts.py`'s renderable prompt — the one prompt a
tool builds rather than the fixed `SYSTEM_PROMPT`."""

from mythrix.agent.prompts import render_passage_summary_prompt


def test_summary_prompt_carries_the_passage_verbatim_and_scopes_to_its_concepts() -> None:
    prompt = render_passage_summary_prompt("And Sara said: God hath made a laughter for me.", ("laughter", "old age"))

    assert "And Sara said: God hath made a laughter for me." in prompt
    assert "laughter, old age" in prompt


def test_summary_prompt_renders_no_citation_markers() -> None:
    """This prompt is deliberately outside the `[G#]`/`[S#]` contract — one
    passage at a time, with nothing to enumerate markers against."""
    prompt = render_passage_summary_prompt("Some retrieved text.", ("fire",))

    assert "[S1]" not in prompt
    assert "[G1]" not in prompt
