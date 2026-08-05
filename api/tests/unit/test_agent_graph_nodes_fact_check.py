# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `agent/graph/nodes/fact_check.py::fact_check_node` (ADR-025)
— the code-level decisions around the one model call it makes: when to skip
it, when to trust its parsed verdicts enough to score them, when to discard
them, and how the score footer gets appended to the *original* answer (the
model is never given the answer's own text to reproduce, so there is nothing
else it could return). No live Ollama; a fake `ChatClient` stands in,
scripted with the JSON response `run_fact_check` parses."""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mythrix.agent.graph.nodes.fact_check import fact_check_node
from mythrix.core.errors import ModelRequestError


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


def _verdicts_response(*results: dict) -> str:
    return json.dumps({"verified": True, "results": list(results)})


def _get_sign_message(grounding_id: str = "G111111") -> ToolMessage:
    payload = {
        "denotation": "Joy and vitality.",
        "interpretants": [],
        "citations": [{"source": "Waite", "locator": "p. 143", "grounding_id": grounding_id}],
    }
    return ToolMessage(content=json.dumps(payload), name="get_sign", tool_call_id="c1")


def _listing_message() -> ToolMessage:
    return ToolMessage(
        content=json.dumps([{"slug": "the-sun", "name": "The Sun"}]), name="list_signs", tool_call_id="c1"
    )


def _state(*, messages: list, turn_start_index: int = 0) -> dict:
    return {"messages": messages, "turn_start_index": turn_start_index}


def test_no_op_when_no_tool_was_called_this_turn() -> None:
    state = _state(messages=[HumanMessage(content="hello"), AIMessage(content="Hi there.")])

    assert fact_check_node(state, FakeChatClient(response="unused")) == {}


def test_no_op_when_only_listing_tools_were_called() -> None:
    state = _state(
        messages=[HumanMessage(content="list signs"), _listing_message(), AIMessage(content="Here are the signs.")]
    )

    assert fact_check_node(state, FakeChatClient(response="unused")) == {}


def test_well_behaved_classification_gets_a_score_footer_on_the_original_answer() -> None:
    """The displayed reply is always the primary model's own original
    answer, verbatim — the fact-checker never receives or returns any of
    the answer's own text, only a per-sentence classification by index."""
    state = _state(
        messages=[
            HumanMessage(content="what does the sun mean"),
            _get_sign_message(),
            AIMessage(content="The Sun symbolizes joy."),
        ]
    )
    client = FakeChatClient(response=_verdicts_response({"index": 0, "supported": True, "citations": ["111111"]}))

    result = fact_check_node(state, client)

    reply = result["messages"][0]
    assert isinstance(reply, AIMessage)
    assert reply.content == "The Sun symbolizes joy.\n###### facts checked: 100%"


def test_a_model_error_falls_back_to_the_original_answer_with_no_footer() -> None:
    state = _state(
        messages=[
            HumanMessage(content="what does the sun mean"),
            _get_sign_message(),
            AIMessage(content="The Sun symbolizes joy."),
        ]
    )
    client = FakeChatClient(raises=ModelRequestError("fake-model", cause="boom"))

    assert fact_check_node(state, client) == {}


def test_an_unparseable_response_falls_back_to_the_original_answer_with_no_footer() -> None:
    state = _state(
        messages=[
            HumanMessage(content="what does the sun mean"),
            _get_sign_message(),
            AIMessage(content="The Sun symbolizes joy."),
        ]
    )
    client = FakeChatClient(response="not json at all")

    assert fact_check_node(state, client) == {}


def test_an_unsupported_claim_lowers_the_score() -> None:
    state = _state(
        messages=[
            HumanMessage(content="what does the sun mean"),
            _get_sign_message(),
            AIMessage(content="The Sun symbolizes joy. It also predicts next week's weather."),
        ]
    )
    client = FakeChatClient(
        response=_verdicts_response(
            {"index": 0, "supported": True, "citations": ["111111"]},
            {"index": 1, "supported": False},
        )
    )

    result = fact_check_node(state, client)

    assert result["messages"][0].content == (
        "The Sun symbolizes joy. It also predicts next week's weather.\n###### facts checked: 50%"
    )


def test_no_op_when_the_classification_tags_nothing() -> None:
    """`grounding_score` is `None` when nothing was classified as a claim —
    a true no-op, not a footer-free copy: the original message stands
    unchanged."""
    state = _state(
        messages=[
            HumanMessage(content="what does the sun mean"),
            _get_sign_message(),
            AIMessage(content="Hello! Happy to help."),
        ]
    )
    client = FakeChatClient(response=_verdicts_response())

    assert fact_check_node(state, client) == {}


def test_markdown_in_the_answer_is_preserved_in_the_scored_reply() -> None:
    """The fact-checker never receives or returns the answer's own text, so
    there is no reproduction step that could drop the answer's markdown —
    the reply the user sees is always the unmodified original."""
    state = _state(
        messages=[
            HumanMessage(content="what does the sun mean"),
            _get_sign_message(),
            AIMessage(content="The **Sun** symbolizes joy."),
        ]
    )
    client = FakeChatClient(response=_verdicts_response({"index": 0, "supported": True, "citations": ["111111"]}))

    result = fact_check_node(state, client)

    assert result["messages"][0].content == "The **Sun** symbolizes joy.\n###### facts checked: 100%"


def test_evidence_is_scoped_to_this_turn_via_turn_start_index() -> None:
    """This turn's own tool messages are found via `turn_start_index`, fixed
    once per turn — an unrelated prior turn earlier in history must not
    affect the evidence this turn's answer is checked against."""
    state = _state(
        messages=[
            HumanMessage(content="unrelated prior turn"),
            AIMessage(content="unrelated prior reply"),
            HumanMessage(content="what does the sun mean"),
            _get_sign_message(),
            AIMessage(content="The Sun symbolizes joy."),
        ],
        turn_start_index=2,
    )
    client = FakeChatClient(response=_verdicts_response({"index": 0, "supported": True, "citations": ["111111"]}))

    result = fact_check_node(state, client)

    assert result["messages"][0].content.startswith("The Sun symbolizes joy.")
