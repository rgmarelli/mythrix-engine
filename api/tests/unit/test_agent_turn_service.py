"""Unit tests for `agent/turn_service.py::run_chat_turn` — drives a stub
tool-calling model through `compile_agent_graph`, no live Ollama involved."""

import logging

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from mythrix.agent.context import AgentUiSelection
from mythrix.agent.graph import compile_agent_graph
from mythrix.agent.sessions import SessionStore
from mythrix.agent.turn_service import AgentInstruction, run_chat_turn
from mythrix.core.errors import ModelRequestError


@tool
def get_sign(sign: str, tradition: str | None = None) -> dict:
    """Fake get_sign mirroring the real tool's needs_tradition shape."""
    if tradition is None:
        return {"needs_tradition": True, "sign": "The Magician", "traditions": ["rider-waite", "marseille"]}
    return {
        "sign": "The Magician",
        "semiotic_system": "tarot",
        "tradition": tradition,
        "citations": [{"source": "Waite", "locator": "p. 1"}],
    }


@tool
def summarize_passage(passage_text: str, concepts: list[str]) -> dict:
    """Fake summarize_passage mirroring the real tool's shape."""
    return {"summary": f"Summary of: {passage_text} ({', '.join(concepts)})"}


@tool
def fetch_segments(source_id: str, start_ordinal: int, end_ordinal: int) -> list[dict]:
    """Fake fetch_segments mirroring the real tool's shape."""
    return [
        {"ordinal": ordinal, "locator": f"{source_id} {ordinal}", "section": None, "text": f"text {ordinal}"}
        for ordinal in range(start_ordinal, end_ordinal + 1)
    ]


_TOOLS = [get_sign, summarize_passage, fetch_segments]


class ScriptedLLM:
    """Emits a pre-programmed sequence of `AIMessage`s in order — one per
    model invocation, across as many turns as the script provides for."""

    def __init__(self, script: list[AIMessage]) -> None:
        self.script = list(script)
        self.calls = 0

    def invoke(self, messages: list) -> AIMessage:
        response = self.script[self.calls]
        self.calls += 1
        return response


def _graph(script: list[AIMessage]):
    return compile_agent_graph(ScriptedLLM(script), _TOOLS)


def test_normal_turn_grounds_the_reply_and_backfills_context() -> None:
    script = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_sign", "args": {"sign": "The Magician", "tradition": "rider-waite"}, "id": "c1"}],
        ),
        AIMessage(content="The Magician represents willpower [G1]."),
    ]
    sessions = SessionStore()

    response = run_chat_turn(
        graph=_graph(script),
        sessions=sessions,
        session_id="s1",
        message="tell me about the magician in rider-waite",
        ui_selection=AgentUiSelection(),
        max_tool_iterations=8,
    )

    assert "[G1]" not in response.reply_text
    assert "willpower" in response.reply_text
    assert response.context.sign == "The Magician"
    assert response.context.tradition == "rider-waite"
    assert response.context.semiotic_system == "tarot"
    # Card output is currently disabled (turn_service.py's FIXME).
    assert response.cards == []
    assert response.thread_reset is False


def test_hotspot_navigation_resets_the_thread() -> None:
    script = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_sign", "args": {"sign": "The Magician", "tradition": "rider-waite"}, "id": "c1"}],
        ),
        AIMessage(content="Noted [G1]."),
        AIMessage(
            content="",
            tool_calls=[{"name": "get_sign", "args": {"sign": "The Magician", "tradition": "rider-waite"}, "id": "c2"}],
        ),
        AIMessage(content="Second reply [G1]."),
    ]
    sessions = SessionStore()
    graph = _graph(script)  # one graph for both turns, so the script advances 0,1 then 2,3

    # The very first turn of a session has no prior region to compare
    # against, so selecting *any* hotspot is itself a reset (the first
    # activation of a thread) — this asserts the interesting case below,
    # the second hotspot change relative to an already-established one.
    run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="tell me about the magician",
        ui_selection=AgentUiSelection(region_id="waite::0-1"),
        max_tool_iterations=8,
    )

    second = run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="tell me about it again",
        ui_selection=AgentUiSelection(region_id="waite::2-3"),
        max_tool_iterations=8,
    )

    assert second.thread_reset is True
    # The raw transcript the model sees must not carry over either — otherwise
    # a bad turn from the old thread keeps getting imitated in the new one.
    # One turn is HumanMessage + tool-call AIMessage + ToolMessage + final
    # AIMessage; a leaking reset would leave the first turn's 4 messages too.
    assert len(sessions.get_or_create("s1").history) == 4


def test_model_driven_reset_drops_the_stale_pre_reset_history_too() -> None:
    script = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_sign", "args": {"sign": "The Magician", "tradition": "rider-waite"}, "id": "c1"}],
        ),
        AIMessage(content="First reply [G1]."),
        AIMessage(
            content="",
            tool_calls=[{"name": "get_sign", "args": {"sign": "The Magician", "tradition": "marseille"}, "id": "c2"}],
        ),
        AIMessage(content="Second reply, different tradition [G1]."),
    ]
    sessions = SessionStore()
    graph = _graph(script)  # one graph for both turns, so the script advances 0,1 then 2,3

    run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="tell me about the magician in rider-waite",
        ui_selection=AgentUiSelection(),
        max_tool_iterations=8,
    )

    second = run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="what about in marseille",
        ui_selection=AgentUiSelection(),
        max_tool_iterations=8,
    )

    assert second.thread_reset is True
    # Same shape as the hotspot-navigation reset: only this turn's own
    # messages survive, not the first turn's now-stale exchange.
    assert len(sessions.get_or_create("s1").history) == 4


def test_ambiguous_tradition_short_circuits_with_no_second_model_call() -> None:
    llm = ScriptedLLM(
        [AIMessage(content="", tool_calls=[{"name": "get_sign", "args": {"sign": "The Magician"}, "id": "c1"}])]
    )
    graph = compile_agent_graph(llm, _TOOLS)
    sessions = SessionStore()

    response = run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="tell me about the magician",
        ui_selection=AgentUiSelection(),
        max_tool_iterations=8,
    )

    assert llm.calls == 1
    assert "rider-waite" in response.reply_text
    assert "marseille" in response.reply_text
    assert response.cards == []
    assert response.context.sign is None


def test_fabricated_citation_marker_is_not_shown_and_history_is_not_persisted() -> None:
    script = [AIMessage(content="This is fabricated [G9].")]
    sessions = SessionStore()

    response = run_chat_turn(
        graph=_graph(script),
        sessions=sessions,
        session_id="s1",
        message="tell me something",
        ui_selection=AgentUiSelection(),
        max_tool_iterations=8,
    )

    assert "[G9]" not in response.reply_text
    assert "fabricated" not in response.reply_text
    assert sessions.get_or_create("s1").history == []


def test_summarize_command_with_active_hotspot_fetches_and_summarizes_deterministically() -> None:
    """FR-AG-33: the reply is the `summarize_passage` tool's own result, and
    the stored `HumanMessage` is the user's literal command — not a
    fabricated directive (FR-AG-36, ADR-012)."""
    sessions = SessionStore()

    response = run_chat_turn(
        graph=_graph([]),
        sessions=sessions,
        session_id="s1",
        message="/summarize",
        ui_selection=AgentUiSelection(region_id="waite::0-1", locator="The Fool"),
        max_tool_iterations=8,
    )

    assert response.reply_text == "Summary of: text 0\n\ntext 1 ()"
    human_messages = [m for m in sessions.get_or_create("s1").history if isinstance(m, HumanMessage)]
    assert [m.content for m in human_messages] == ["/summarize"]


def test_summarize_command_with_no_hotspot_asks_the_user_to_select_one_without_calling_the_model() -> None:
    class ExplodingLLM:
        def invoke(self, messages: list) -> AIMessage:
            raise AssertionError("model was invoked for a /summarize turn with no active hotspot")

    sessions = SessionStore()
    graph = compile_agent_graph(ExplodingLLM(), _TOOLS)

    response = run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="/summarize",
        ui_selection=AgentUiSelection(),
        max_tool_iterations=8,
    )

    assert response.cards == []
    assert "select" in response.reply_text.lower()
    human_messages = [m for m in sessions.get_or_create("s1").history if isinstance(m, HumanMessage)]
    assert [m.content for m in human_messages] == ["/summarize"]


def test_summarize_command_with_no_hotspot_calls_no_tool() -> None:
    @tool("fetch_segments")
    def exploding_fetch_segments(source_id: str, start_ordinal: int, end_ordinal: int) -> list[dict]:
        """Fake fetch_segments that fails the test if ever invoked."""
        raise AssertionError("fetch_segments was invoked for a /summarize turn with no active hotspot")

    sessions = SessionStore()
    graph = compile_agent_graph(ScriptedLLM([]), [exploding_fetch_segments, summarize_passage])

    run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="/summarize",
        ui_selection=AgentUiSelection(),
        max_tool_iterations=8,
    )


def test_summarize_command_includes_trailing_focus_text_as_the_sole_concept() -> None:
    sessions = SessionStore()

    response = run_chat_turn(
        graph=_graph([]),
        sessions=sessions,
        session_id="s1",
        message="/summarize focus on redemption imagery",
        ui_selection=AgentUiSelection(region_id="waite::0-1", locator="The Fool"),
        max_tool_iterations=8,
    )

    assert "redemption imagery" in response.reply_text


def test_an_ordinary_turn_after_summarize_sees_the_summary_in_history() -> None:
    """FR-AG-36 — the opposite of `/query`'s FR-AQ-16 exclusion: a
    `/summarize` turn is ordinary conversation, not a side-effecting command,
    so later turns can refer back to it."""
    sessions = SessionStore()
    graph = _graph([AIMessage(content="Noted the fire imagery.")])

    run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="/summarize",
        ui_selection=AgentUiSelection(region_id="waite::0-1", locator="The Fool"),
        max_tool_iterations=8,
    )
    run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="tell me more about that",
        ui_selection=AgentUiSelection(region_id="waite::0-1", locator="The Fool"),
        max_tool_iterations=8,
    )

    history = sessions.get_or_create("s1").history
    assert any("Summary of" in str(m.content) for m in history)


class ExplodingLLM:
    """Fails the test if the model is consulted at all — how the ad-hoc
    command path's "no generation model" guarantee (agnostic-query.md
    FR-AQ-01) is asserted structurally rather than by output shape."""

    def invoke(self, messages: list) -> AIMessage:
        raise AssertionError("model was invoked for an ad-hoc command turn")


def _adhoc_graph():  # noqa: ANN202 - CompiledStateGraph, matching `_graph` above
    return compile_agent_graph(ExplodingLLM(), _TOOLS)


def _turn(graph, sessions: SessionStore, message: str, **overrides):  # noqa: ANN001, ANN003, ANN202
    return run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message=message,
        ui_selection=overrides.pop("ui_selection", AgentUiSelection()),
        max_tool_iterations=8,
    )


def _confirm_command(response) -> str:  # noqa: ANN001 - AgentTurnResponse
    return response.instructions[0].payload["confirm_command"]


def test_query_command_parses_deterministically_and_asks_for_confirmation() -> None:
    sessions = SessionStore()

    response = _turn(_adhoc_graph(), sessions, "/query laughter, hundred:exact")

    assert "- laughter" in response.reply_text
    assert "- hundred [exact]" in response.reply_text
    assert [i.type for i in response.instructions] == ["confirm_query"]
    assert response.instructions[0].payload["terms"] == [
        {"value": "laughter", "directive": None},
        {"value": "hundred", "directive": "exact"},
    ]
    assert _confirm_command(response) in response.reply_text


def test_query_command_turn_adds_nothing_to_conversation_history() -> None:
    """FR-AQ-16 — the model must never see these turns, so a later reply
    cannot imitate the confirm command or claim a query was run."""
    sessions = SessionStore()

    _turn(_adhoc_graph(), sessions, "/query laughter")

    assert sessions.get_or_create("s1").history == []


def test_an_ordinary_turn_after_a_query_command_sees_history_as_if_it_never_happened() -> None:
    sessions = SessionStore()
    _turn(_adhoc_graph(), sessions, "/query laughter")

    script = [AIMessage(content="Hello there.")]
    llm = ScriptedLLM(script)
    _turn(compile_agent_graph(llm, _TOOLS), sessions, "hello")

    history = sessions.get_or_create("s1").history
    assert [m.content for m in history if isinstance(m, HumanMessage)] == ["hello"]


def test_confirming_emits_execute_query_and_consumes_the_pending_query() -> None:
    sessions = SessionStore()
    graph = _adhoc_graph()
    parsed = _turn(graph, sessions, "/query laughter, hundred:exact")

    confirmed = _turn(graph, sessions, _confirm_command(parsed))

    assert confirmed.instructions == [
        AgentInstruction(
            type="execute_query",
            payload={"terms": [{"value": "laughter", "directive": None}, {"value": "hundred", "directive": "exact"}]},
        )
    ]
    assert _turn(graph, sessions, _confirm_command(parsed)).instructions == []


def test_a_wrong_id_executes_nothing_and_keeps_the_pending_query_alive() -> None:
    sessions = SessionStore()
    graph = _adhoc_graph()
    parsed = _turn(graph, sessions, "/query laughter")

    assert _turn(graph, sessions, "/query-confirm deadbeef").instructions == []
    assert [i.type for i in _turn(graph, sessions, _confirm_command(parsed)).instructions] == ["execute_query"]


def test_a_second_query_command_supersedes_the_first() -> None:
    sessions = SessionStore()
    graph = _adhoc_graph()
    first = _turn(graph, sessions, "/query laughter")
    second = _turn(graph, sessions, "/query child")

    assert _turn(graph, sessions, _confirm_command(first)).instructions == []
    assert _turn(graph, sessions, _confirm_command(second)).instructions == [
        AgentInstruction(type="execute_query", payload={"terms": [{"value": "child", "directive": None}]})
    ]


def test_a_thread_reset_discards_the_pending_query() -> None:
    sessions = SessionStore()
    graph = _adhoc_graph()
    parsed = _turn(graph, sessions, "/query laughter", ui_selection=AgentUiSelection(region_id="waite::0-2"))

    confirmed = _turn(graph, sessions, _confirm_command(parsed), ui_selection=AgentUiSelection(region_id="waite::9-11"))

    assert confirmed.thread_reset is True
    assert confirmed.instructions == []


def test_a_malformed_query_command_creates_no_pending_query() -> None:
    sessions = SessionStore()
    graph = _adhoc_graph()

    response = _turn(graph, sessions, "/query hundred:skip")

    assert response.instructions == []
    assert "skip" in response.reply_text
    assert _turn(graph, sessions, "/query-confirm deadbeef").instructions == []


def test_a_term_shaped_like_a_citation_marker_does_not_fail_the_turn() -> None:
    """The reply restates the user's own terms and is backend-authored, so
    citation validation — which polices model text (FR-AG-06) — must not run
    on it, or `[S1]` would replace the whole turn with the failure message."""
    sessions = SessionStore()

    response = _turn(_adhoc_graph(), sessions, "/query [S1]")

    assert "[S1]" in response.reply_text
    assert [i.type for i in response.instructions] == ["confirm_query"]


class RaisingLLM:
    """Simulates a mid-turn model failure (`ModelRequestError`, a
    `MythrixError`) so `run_chat_turn`'s tool-failure branch can be
    exercised without a live Ollama."""

    def invoke(self, messages: list) -> AIMessage:
        raise ModelRequestError("test-model", cause="boom")


def test_plain_turn_logs_start_context_and_outcome(caplog: pytest.LogCaptureFixture) -> None:
    script = [AIMessage(content="Hello there.")]
    sessions = SessionStore()

    with caplog.at_level(logging.INFO, logger="mythrix.agent.turn_service"):
        run_chat_turn(
            graph=_graph(script),
            sessions=sessions,
            session_id="s1",
            message="hi",
            ui_selection=AgentUiSelection(),
            max_tool_iterations=8,
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any("turn start" in m and "s1" in m for m in messages)
    assert any("resolved context" in m for m in messages)
    assert any("turn outcome" in m for m in messages)


def test_tool_failure_logs_and_returns_fallback(caplog: pytest.LogCaptureFixture) -> None:
    graph = compile_agent_graph(RaisingLLM(), _TOOLS)
    sessions = SessionStore()

    with caplog.at_level(logging.INFO, logger="mythrix.agent.turn_service"):
        response = run_chat_turn(
            graph=graph,
            sessions=sessions,
            session_id="s1",
            message="tell me about the magician",
            ui_selection=AgentUiSelection(),
            max_tool_iterations=8,
        )

    assert "problem reaching one of Mythrix" in response.reply_text
    messages = [record.getMessage() for record in caplog.records]
    assert any("turn failed" in m and "tool error" in m for m in messages)
    assert any("turn outcome" in m for m in messages)


def test_citation_failure_logs_and_returns_fallback(caplog: pytest.LogCaptureFixture) -> None:
    script = [AIMessage(content="This is fabricated [G9].")]
    sessions = SessionStore()

    with caplog.at_level(logging.INFO, logger="mythrix.agent.turn_service"):
        response = run_chat_turn(
            graph=_graph(script),
            sessions=sessions,
            session_id="s1",
            message="tell me something",
            ui_selection=AgentUiSelection(),
            max_tool_iterations=8,
        )

    assert "[G9]" not in response.reply_text
    messages = [record.getMessage() for record in caplog.records]
    assert any("turn failed" in m and "citation validation" in m for m in messages)
