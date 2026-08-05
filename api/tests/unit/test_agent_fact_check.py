# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `agent/fact_check.py` — the narrow model call itself,
decoupled from the graph (ADR-025): `split_sentences` (the deterministic
split the model never touches), `run_fact_check`/its JSON parsing, and
`grounding_score` (the code-side scoring rule)."""

import json
import logging

import pytest

from mythrix.agent.citation_grounding import Evidence
from mythrix.agent.fact_check import SentenceVerdict, grounding_score, is_grounded, run_fact_check, split_sentences
from mythrix.core.errors import ModelRequestError

_EVIDENCE = [Evidence(grounding_id="G111111", source="Waite", locator="p. 143", text="Joy and vitality.")]


class FakeChatClient:
    generation_model = "fake-model"

    def __init__(self, response: str | None = None, raises: Exception | None = None) -> None:
        self._response = response
        self._raises = raises
        self.last_prompt: str | None = None

    def invoke(self, prompt: str) -> str:
        self.last_prompt = prompt
        if self._raises is not None:
            raise self._raises
        assert self._response is not None
        return self._response


def _results_json(**overrides: object) -> str:
    payload = {"verified": True, "results": [{"index": 0, "supported": True, "citations": ["G111111"]}]}
    payload.update(overrides)
    return json.dumps(payload)


# --- split_sentences ---


def test_split_sentences_splits_on_terminal_punctuation() -> None:
    assert split_sentences("The Sun symbolizes joy. It is associated with Mercury.") == (
        "The Sun symbolizes joy.",
        "It is associated with Mercury.",
    )


def test_split_sentences_handles_question_and_exclamation_marks() -> None:
    assert split_sentences("Hello! What does the Sun mean?") == ("Hello!", "What does the Sun mean?")


def test_split_sentences_on_text_with_no_terminal_punctuation_is_one_sentence() -> None:
    assert split_sentences("Joy and vitality") == ("Joy and vitality",)


def test_split_sentences_on_empty_or_whitespace_text_is_empty() -> None:
    assert split_sentences("") == ()
    assert split_sentences("   \n  ") == ()


def test_split_sentences_strips_surrounding_whitespace() -> None:
    assert split_sentences("  The Sun symbolizes joy.  ") == ("The Sun symbolizes joy.",)


def test_split_sentences_strips_list_markers_and_markdown_decoration() -> None:
    text = "Evidence:\n- **Passages**: Genesis 1:5 says light is good.\n1. Second point here."
    assert split_sentences(text) == (
        "Evidence:",
        "Passages: Genesis 1:5 says light is good.",
        "Second point here.",
    )


def test_split_sentences_treats_a_line_break_as_a_sentence_boundary() -> None:
    """A header line with no terminal punctuation (e.g. a `"Key points:"`
    lead-in before a list) survives as its own sentence rather than fusing
    with the next line's first clause — a line break is a boundary on its
    own, not just whitespace to collapse."""
    text = "Key points:\nAbraham was 100 years old. This highlights divine intervention."
    assert split_sentences(text) == (
        "Key points:",
        "Abraham was 100 years old.",
        "This highlights divine intervention.",
    )


def test_split_sentences_does_not_fragment_a_numbered_list_on_the_marker_itself() -> None:
    """Regression test for a real production reply: without list-marker
    stripping, the period in a `1.`/`2.` marker reads as its own sentence
    end, producing a garbage fragment like `"Key points:  \\n1."` instead of
    real sentences."""
    text = (
        "Overview.  \n"
        "1. **Isaac's Age**: Abraham was 100, Sarah 90, yet they had a child. "
        "This highlights divine intervention.  \n"
        '2. **Sarah\'s Joy**: She called the child "laughter" (a metaphor for joy).  \n'
    )
    sentences = split_sentences(text)

    assert "1." not in sentences
    assert not any(s.endswith("1.") or s.endswith("2.") for s in sentences)
    assert sentences == (
        "Overview.",
        "Isaac's Age: Abraham was 100, Sarah 90, yet they had a child.",
        "This highlights divine intervention.",
        'Sarah\'s Joy: She called the child "laughter" (a metaphor for joy).',
    )


def test_split_sentences_does_not_fragment_a_page_citation_abbreviation() -> None:
    """Regression test for a real production reply: `"(p. 143)"` used to
    split into `'...(p.'` and `'143), where it is...'` — the period in `p.`
    read as a sentence end because it happened to be followed by whitespace,
    same as any other terminal punctuation. The fragment carried no claim of
    its own and a real model (phi4-mini) simply dropped it from its
    classification results, silently undercounting the answer's claims."""
    text = (
        "Its interpretant is joy, as noted in The Pictorial Key to the Tarot "
        "(p. 143), where it is described as a symbol of positive energy."
    )
    assert split_sentences(text) == (
        "Its interpretant is joy, as noted in The Pictorial Key to the Tarot "
        "(p. 143), where it is described as a symbol of positive energy.",
    )


def test_split_sentences_still_splits_normally_around_a_digit_free_boundary() -> None:
    assert split_sentences("Sentence one. Sentence two.") == ("Sentence one.", "Sentence two.")


# --- run_fact_check / JSON parsing ---


def test_run_fact_check_returns_none_on_a_model_error() -> None:
    client = FakeChatClient(raises=ModelRequestError("fake-model", cause="boom"))

    result = run_fact_check(client, evidence=_EVIDENCE, sentences=("The Sun symbolizes joy.",))

    assert result is None


def test_run_fact_check_prompt_carries_the_sentences_and_evidence() -> None:
    client = FakeChatClient(response=_results_json())

    run_fact_check(client, evidence=_EVIDENCE, sentences=("The Sun symbolizes joy.",))

    assert client.last_prompt is not None
    assert "[111111]" in client.last_prompt
    assert "G111111" not in client.last_prompt
    assert "Joy and vitality." in client.last_prompt
    assert '"index": 0' in client.last_prompt
    assert '"text": "The Sun symbolizes joy."' in client.last_prompt


def test_run_fact_check_prompt_states_the_completion_contract() -> None:
    """The prompt hands the model a pre-filled JSON document (one entry per
    sentence, `index`/`text` already set, `supported`/`citations` null/empty)
    and asks it to complete rather than generate `results` — nothing to
    omit, only nulls to fill in."""
    client = FakeChatClient(response=_results_json())

    run_fact_check(client, evidence=_EVIDENCE, sentences=("One.", "Two.", "Three."))

    assert client.last_prompt is not None
    assert "Your task is to complete the JSON" in client.last_prompt
    assert "Do NOT add, remove, reorder, or rename any objects or fields" in client.last_prompt
    assert 'Do NOT modify the values of "index" or "text"' in client.last_prompt
    for i, sentence in enumerate(("One.", "Two.", "Three.")):
        assert f'"index": {i}' in client.last_prompt
        assert f'"text": "{sentence}"' in client.last_prompt
    assert '"supported": null' in client.last_prompt


def test_run_fact_check_logs_the_rendered_prompt_and_the_raw_response(caplog: pytest.LogCaptureFixture) -> None:
    """The parsed verdicts alone don't show what the model was actually
    asked to classify — logged at `INFO`, mirroring `agent_node`'s own
    `model input`/`model output` logging for the primary model. The response
    logs pretty-printed, not as a `%r`-escaped single line, so it's actually
    readable rather than a wall of literal `\\n`s."""
    client = FakeChatClient(response=_results_json())

    with caplog.at_level(logging.INFO, logger="mythrix.agent.fact_check"):
        run_fact_check(client, evidence=_EVIDENCE, sentences=("The Sun symbolizes joy.",))

    assert "fact-check model input" in caplog.text
    assert '"text": "The Sun symbolizes joy."' in caplog.text
    assert "fact-check model output" in caplog.text
    assert '"index": 0' in caplog.text
    assert '"supported": true' in caplog.text
    assert "\\n" not in caplog.text


def test_run_fact_check_logs_a_non_json_response_as_is(caplog: pytest.LogCaptureFixture) -> None:
    """A response that never parses as JSON at all (the actual model-call
    failure case, not just a malformed entry) logs unmodified rather than
    silently disappearing behind a failed pretty-print attempt."""
    client = FakeChatClient(response="I cannot classify these sentences.")

    with caplog.at_level(logging.INFO, logger="mythrix.agent.fact_check"):
        run_fact_check(client, evidence=_EVIDENCE, sentences=("The Sun symbolizes joy.",))

    assert "I cannot classify these sentences." in caplog.text


def test_run_fact_check_parses_clean_json_into_verdicts() -> None:
    client = FakeChatClient(response=_results_json())

    result = run_fact_check(client, evidence=_EVIDENCE, sentences=("The Sun symbolizes joy.",))

    assert result == (SentenceVerdict(index=0, supported=True, citations=("G111111",)),)


def test_run_fact_check_tolerates_an_index_the_model_left_out_of_results() -> None:
    """The model can still simply not return an entry for some index at
    all — that index contributes no verdict, same as an explicit
    `"supported": null`."""
    payload = {"verified": True, "results": [{"index": 1, "supported": False}]}
    client = FakeChatClient(response=json.dumps(payload))

    result = run_fact_check(client, evidence=_EVIDENCE, sentences=("Hello!", "It predicts the weather."))

    assert result == (SentenceVerdict(index=1, supported=False, citations=()),)


def test_run_fact_check_skips_an_entry_marked_supported_null() -> None:
    """`"supported": null` is the prompt's explicit way of saying "no
    factual claim here" — it contributes no verdict, same as an absent
    index. The model's own echoed `"text"` for the skipped entry is never
    read, only its `"index"`."""
    payload = {
        "results": [
            {"index": 0, "text": "Hello!", "supported": None, "citations": []},
            {"index": 1, "text": "The Sun symbolizes joy.", "supported": True, "citations": ["G111111"]},
        ]
    }
    client = FakeChatClient(response=json.dumps(payload))

    result = run_fact_check(client, evidence=_EVIDENCE, sentences=("Hello!", "The Sun symbolizes joy."))

    assert result == (SentenceVerdict(index=1, supported=True, citations=("G111111",)),)


def test_run_fact_check_strips_a_markdown_json_fence() -> None:
    client = FakeChatClient(response=f"```json\n{_results_json()}\n```")

    result = run_fact_check(client, evidence=_EVIDENCE, sentences=("The Sun symbolizes joy.",))

    assert result == (SentenceVerdict(index=0, supported=True, citations=("G111111",)),)


def test_run_fact_check_extracts_json_from_surrounding_prose() -> None:
    client = FakeChatClient(response=f"Here is the classification:\n{_results_json()}\nHope that helps!")

    result = run_fact_check(client, evidence=_EVIDENCE, sentences=("The Sun symbolizes joy.",))

    assert result == (SentenceVerdict(index=0, supported=True, citations=("G111111",)),)


def test_run_fact_check_returns_none_on_malformed_json() -> None:
    client = FakeChatClient(response="not json at all")

    result = run_fact_check(client, evidence=_EVIDENCE, sentences=("The Sun symbolizes joy.",))

    assert result is None


def test_run_fact_check_returns_none_when_results_key_is_missing() -> None:
    client = FakeChatClient(response=json.dumps({"verified": True}))

    result = run_fact_check(client, evidence=_EVIDENCE, sentences=("The Sun symbolizes joy.",))

    assert result is None


def test_run_fact_check_skips_an_entry_with_an_out_of_range_index_but_keeps_the_rest() -> None:
    payload = {
        "results": [
            {"index": 5, "supported": True, "citations": ["G111111"]},
            {"index": 0, "supported": False},
        ]
    }
    client = FakeChatClient(response=json.dumps(payload))

    result = run_fact_check(client, evidence=_EVIDENCE, sentences=("The Sun symbolizes joy.",))

    assert result == (SentenceVerdict(index=0, supported=False, citations=()),)


def test_run_fact_check_skips_an_entry_with_a_non_boolean_supported_field() -> None:
    payload = {"results": [{"index": 0, "supported": "yes"}]}
    client = FakeChatClient(response=json.dumps(payload))

    result = run_fact_check(client, evidence=_EVIDENCE, sentences=("The Sun symbolizes joy.",))

    assert result == ()


def test_run_fact_check_strips_brackets_a_model_echoes_around_a_citation_id() -> None:
    """Regression: the evidence block labels each item as `[id]`, and a
    real model sometimes echoes a citation back the same bracketed way
    instead of as the bare id `grounding_score` compares against — which,
    unstripped, makes a correctly cited claim fail to match and score as
    unsupported."""
    payload = {"results": [{"index": 0, "supported": True, "citations": ["[G111111]"]}]}
    client = FakeChatClient(response=json.dumps(payload))

    result = run_fact_check(client, evidence=_EVIDENCE, sentences=("The Sun symbolizes joy.",))

    assert result == (SentenceVerdict(index=0, supported=True, citations=("G111111",)),)


def test_run_fact_check_keeps_the_first_entry_on_a_duplicate_index() -> None:
    payload = {
        "results": [
            {"index": 0, "supported": True, "citations": ["G111111"]},
            {"index": 0, "supported": False},
        ]
    }
    client = FakeChatClient(response=json.dumps(payload))

    result = run_fact_check(client, evidence=_EVIDENCE, sentences=("The Sun symbolizes joy.",))

    assert result == (SentenceVerdict(index=0, supported=True, citations=("G111111",)),)


# --- grounding_score ---


def test_grounding_score_all_verdicts_supported_with_valid_citations() -> None:
    verdicts = (
        SentenceVerdict(index=0, supported=True, citations=("G1",)),
        SentenceVerdict(index=1, supported=True, citations=("S1",)),
    )
    assert grounding_score(verdicts, {"G1", "S1"}) == 1.0


def test_grounding_score_all_verdicts_unsupported() -> None:
    verdicts = (SentenceVerdict(index=0, supported=False), SentenceVerdict(index=1, supported=False))
    assert grounding_score(verdicts, {"G1", "S1"}) == 0.0


def test_grounding_score_mixed_verdicts() -> None:
    verdicts = (
        SentenceVerdict(index=0, supported=True, citations=("G1",)),
        SentenceVerdict(index=1, supported=False),
        SentenceVerdict(index=2, supported=True, citations=("S1",)),
    )
    assert grounding_score(verdicts, {"G1", "S1"}) == 2 / 3


def test_grounding_score_supported_true_with_no_valid_citation_counts_as_unsupported() -> None:
    """The boolean alone is never trusted: a claim tagged supported with an
    empty or entirely hallucinated citation list is exactly as ungrounded as
    one tagged unsupported outright."""
    verdicts = (
        SentenceVerdict(index=0, supported=True, citations=()),
        SentenceVerdict(index=1, supported=True, citations=("G9",)),
    )
    assert grounding_score(verdicts, {"G1"}) == 0.0


def test_grounding_score_none_when_there_are_no_verdicts() -> None:
    """Distinct from `0.0`: no verdicts means nothing was classified as a
    claim at all, not that every claim was unsupported."""
    assert grounding_score((), {"G1"}) is None


# --- is_grounded ---


def test_is_grounded_true_for_a_supported_verdict_with_a_valid_citation() -> None:
    assert is_grounded(SentenceVerdict(index=0, supported=True, citations=("G1",)), {"G1"}) is True


def test_is_grounded_false_for_an_unsupported_verdict_even_with_a_valid_citation() -> None:
    assert is_grounded(SentenceVerdict(index=0, supported=False, citations=("G1",)), {"G1"}) is False


def test_is_grounded_false_for_a_supported_verdict_with_no_valid_citation() -> None:
    assert is_grounded(SentenceVerdict(index=0, supported=True, citations=("G9",)), {"G1"}) is False
    assert is_grounded(SentenceVerdict(index=0, supported=True, citations=()), {"G1"}) is False


def test_is_grounded_warns_on_an_invented_citation_even_when_a_real_one_saves_the_verdict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A hallucinated id riding alongside a real one still counts the
    sentence as grounded (the real citation carries it) — but the model
    invented a citation, and that should not be silent."""
    with caplog.at_level(logging.WARNING, logger="mythrix.agent.fact_check"):
        result = is_grounded(SentenceVerdict(index=1, supported=True, citations=("G1", "Sse60ed")), {"G1"})

    assert result is True
    assert "Sse60ed" in caplog.text
    assert "invented by LLM" in caplog.text
