"""Unit tests for `agent/turn_service.py::run_chat_turn` — drives a stub
tool-calling model through `compile_agent_graph`, no live Ollama involved."""

import logging

import pytest
from graph_helpers import compile_graph
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from mythrix.agent.context import AgentContext
from mythrix.agent.sessions import SessionStore
from mythrix.agent.turn_service import AgentInstruction, run_chat_turn
from mythrix.core.errors import ModelRequestError


@tool
def get_sign(sign: str, tradition: str | None = None) -> dict:
    """Fake get_sign mirroring the real tool's needs_tradition shape, and its
    slug identity keys / `*_name` display keys (ADR-014)."""
    if tradition is None:
        return {
            "needs_tradition": True,
            "sign": "the-magician",
            "sign_name": "The Magician",
            "traditions": [
                {"slug": "rider-waite", "name": "Rider-Waite-Smith"},
                {"slug": "marseille", "name": "Tarot de Marseille"},
            ],
        }
    return {
        "sign": "the-magician",
        "sign_name": "The Magician",
        "semiotic_system": "tarot",
        "tradition": "rider-waite",
        "tradition_name": "Rider-Waite-Smith",
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


@tool
def list_signs(semiotic_system: str | None = None) -> list[dict]:
    """Fake list_signs mirroring the real tool's shape — no `citations` field."""
    return [
        {"slug": "aleph", "name": "Aleph", "semiotic_system": "hebrew_alef_bet", "traditions": ["sepher-yetzirah-gra"]}
    ]


_TOOLS = [get_sign, summarize_passage, fetch_segments, list_signs]


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
    return compile_graph(ScriptedLLM(script), _TOOLS)


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
        ui_selection=AgentContext(),
        max_tool_iterations=8,
    )

    assert "[G1]" not in response.reply_text
    assert "willpower" in response.reply_text
    assert response.context.sign == "the-magician"
    assert response.context.tradition == "rider-waite"
    assert response.context.semiotic_system == "tarot"
    assert response.thread_reset is False


def test_get_sign_leaves_the_uis_own_selection_byte_identical() -> None:
    """The invariant this change exists to establish: a turn that resolves the
    same entities the browser already selected returns them spelled exactly as
    the browser sent them, so the context stays comparable as identity
    (ADR-014). Before, `get_sign` overwrote "rider-waite" with
    "Rider-Waite-Smith" and every later turn read as a subject change."""
    call = {"name": "get_sign", "args": {"sign": "The Magician", "tradition": "rider-waite"}, "id": "c1"}
    script = [
        AIMessage(content="", tool_calls=[call]),
        AIMessage(content="Willpower [G1]."),
        AIMessage(content="", tool_calls=[{**call, "id": "c2"}]),
        AIMessage(content="Still willpower [G1]."),
    ]
    selection = AgentContext(sign="the-magician", tradition="rider-waite", semiotic_system="tarot")
    sessions, graph = SessionStore(), _graph(script)

    def _turn():  # noqa: ANN202
        return run_chat_turn(
            graph=graph,
            sessions=sessions,
            session_id="s1",
            message="tell me about it",
            ui_selection=selection,
            max_tool_iterations=8,
        )

    # The first turn establishes the thread — a selection against an empty
    # stored context is itself a reset. The second is the one that regressed.
    first = _turn()
    second = _turn()

    for response in (first, second):
        assert response.context.sign == selection.sign
        assert response.context.tradition == selection.tradition
        assert response.context.semiotic_system == selection.semiotic_system
    assert second.thread_reset is False


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
        ui_selection=AgentContext(region_id="waite::0-1"),
        max_tool_iterations=8,
    )

    second = run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="tell me about it again",
        ui_selection=AgentContext(region_id="waite::2-3"),
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
        ui_selection=AgentContext(),
        max_tool_iterations=8,
    )

    second = run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="what about in marseille",
        ui_selection=AgentContext(),
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
    graph = compile_graph(llm, _TOOLS)
    sessions = SessionStore()

    response = run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="tell me about the magician",
        ui_selection=AgentContext(),
        max_tool_iterations=8,
    )

    assert llm.calls == 1
    # The user is asked in display names, not slugs (FR-AG-07, ADR-014).
    assert "Rider-Waite-Smith" in response.reply_text
    assert "Tarot de Marseille" in response.reply_text
    assert response.context.sign is None


def test_fabricated_citation_marker_is_not_shown_and_history_is_not_persisted() -> None:
    script = [AIMessage(content="This is fabricated [G9].")]
    sessions = SessionStore()

    response = run_chat_turn(
        graph=_graph(script),
        sessions=sessions,
        session_id="s1",
        message="tell me something",
        ui_selection=AgentContext(),
        max_tool_iterations=8,
    )

    assert "[G9]" not in response.reply_text
    assert "fabricated" not in response.reply_text
    assert sessions.get_or_create("s1").history == []


def test_stray_marker_on_a_listing_tool_reply_is_stripped_not_rejected() -> None:
    """`list_signs` has no `citations` field for any marker to ever be valid
    against (unlike `get_sign`) — a marker the model wrongly attaches to it
    is a formatting slip on real, tool-derived data, not the FR-AG-06
    fabrication risk citation validation exists to catch, so the turn
    succeeds with the marker stripped rather than being discarded."""
    script = [
        AIMessage(
            content="",
            tool_calls=[{"name": "list_signs", "args": {"semiotic_system": "hebrew_alef_bet"}, "id": "c1"}],
        ),
        AIMessage(content="[G1] Aleph"),
    ]
    sessions = SessionStore()

    response = run_chat_turn(
        graph=_graph(script),
        sessions=sessions,
        session_id="s1",
        message="list signs from hebrew_alef_bet",
        ui_selection=AgentContext(),
        max_tool_iterations=8,
    )

    assert "[G1]" not in response.reply_text
    assert "Aleph" in response.reply_text
    assert sessions.get_or_create("s1").history != []


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
        ui_selection=AgentContext(region_id="waite::0-1", locator="The Fool"),
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
    graph = compile_graph(ExplodingLLM(), _TOOLS)

    response = run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="/summarize",
        ui_selection=AgentContext(),
        max_tool_iterations=8,
    )

    assert "select" in response.reply_text.lower()
    human_messages = [m for m in sessions.get_or_create("s1").history if isinstance(m, HumanMessage)]
    assert [m.content for m in human_messages] == ["/summarize"]


def test_summarize_command_with_no_hotspot_calls_no_tool() -> None:
    @tool("fetch_segments")
    def exploding_fetch_segments(source_id: str, start_ordinal: int, end_ordinal: int) -> list[dict]:
        """Fake fetch_segments that fails the test if ever invoked."""
        raise AssertionError("fetch_segments was invoked for a /summarize turn with no active hotspot")

    sessions = SessionStore()
    graph = compile_graph(ScriptedLLM([]), [exploding_fetch_segments, summarize_passage])

    run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="/summarize",
        ui_selection=AgentContext(),
        max_tool_iterations=8,
    )


def test_summarize_command_includes_trailing_focus_text_as_the_sole_concept() -> None:
    sessions = SessionStore()

    response = run_chat_turn(
        graph=_graph([]),
        sessions=sessions,
        session_id="s1",
        message="/summarize focus on redemption imagery",
        ui_selection=AgentContext(region_id="waite::0-1", locator="The Fool"),
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
        ui_selection=AgentContext(region_id="waite::0-1", locator="The Fool"),
        max_tool_iterations=8,
    )
    run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="tell me more about that",
        ui_selection=AgentContext(region_id="waite::0-1", locator="The Fool"),
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
    return compile_graph(ExplodingLLM(), _TOOLS)


def _turn(graph, sessions: SessionStore, message: str, **overrides):  # noqa: ANN001, ANN003, ANN202
    return run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message=message,
        ui_selection=overrides.pop("ui_selection", AgentContext()),
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
    _turn(compile_graph(llm, _TOOLS), sessions, "hello")

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
    parsed = _turn(graph, sessions, "/query laughter", ui_selection=AgentContext(region_id="waite::0-2"))

    confirmed = _turn(graph, sessions, _confirm_command(parsed), ui_selection=AgentContext(region_id="waite::9-11"))

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
            ui_selection=AgentContext(),
            max_tool_iterations=8,
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any("turn start" in m and "s1" in m for m in messages)
    assert any("resolved context" in m for m in messages)
    assert any("turn outcome" in m for m in messages)


def test_tool_failure_logs_and_returns_fallback(caplog: pytest.LogCaptureFixture) -> None:
    graph = compile_graph(RaisingLLM(), _TOOLS)
    sessions = SessionStore()

    with caplog.at_level(logging.INFO, logger="mythrix.agent.turn_service"):
        response = run_chat_turn(
            graph=graph,
            sessions=sessions,
            session_id="s1",
            message="tell me about the magician",
            ui_selection=AgentContext(),
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
            ui_selection=AgentContext(),
            max_tool_iterations=8,
        )

    assert "[G9]" not in response.reply_text
    messages = [record.getMessage() for record in caplog.records]
    assert any("turn failed" in m and "citation validation" in m for m in messages)


# --- corpus discovery (discovery.md FR-DS-22–FR-DS-28) --------------------


@tool
def query_adhoc(terms: list[dict], limit: int) -> dict:
    """Fake query_adhoc mirroring the real tool's shape."""
    return {
        "matched_count": 2,
        "regions": [
            {
                "region_id": f"waite::{i * 10}-{i * 10 + 1}",
                "source": "Douay-Rheims",
                "source_id": "waite",
                "locator": f"Genesis {i + 1}:6",
                "score": 0.8,
                "convergence_count": 1,
                "matches": [],
            }
            for i in range(2)
        ],
    }


@tool
def analyze_passage(passage_text: str, focus: str, concepts: list[str]) -> dict:
    """Fake analyze_passage mirroring the real tool's shape."""
    return {"finding": "a finding"}


def _discovery_graph(consolidation: str):  # noqa: ANN202 - CompiledStateGraph
    @tool
    def consolidate_findings(focus: str, findings: list[dict], concepts: list[str]) -> dict:
        """Fake consolidate_findings returning a scripted consolidation."""
        return {"consolidation": consolidation}

    return compile_graph(ExplodingLLM(), _TOOLS, node_tools=[query_adhoc, analyze_passage, consolidate_findings])


def _plan_and_confirm(graph, sessions: SessionStore, consolidation_graph=None):  # noqa: ANN001, ANN202
    plan = _turn(graph, sessions, '/discover "where joy is", laughter')
    discovery_id = sessions.get_or_create("s1").pending_discovery.id
    return plan, _turn(consolidation_graph or graph, sessions, f"/discover-confirm {discovery_id}")


def test_a_discovery_run_keeps_its_region_markers_in_the_delivered_reply() -> None:
    """FR-DS-23: `[R#]` is validated like every other marker but retained, so
    a consolidated claim can be traced to the section supporting it."""
    sessions = SessionStore()

    _, run = _plan_and_confirm(_discovery_graph("Joy recurs as reversal [R1][R2]."), sessions)

    assert "Joy recurs as reversal [R1][R2]." in run.reply_text
    assert "### [R1] Douay-Rheims — Genesis 1:6" in run.reply_text


def test_a_consolidation_citing_a_region_that_does_not_exist_fails_the_turn() -> None:
    """FR-DS-22: region markers are validated exactly as graph-fact and
    segment markers are — two regions were read, so `[R9]` names nothing."""
    sessions = SessionStore()

    _, run = _plan_and_confirm(_discovery_graph("Joy recurs [R9]."), sessions)

    assert "[R9]" not in run.reply_text
    assert "couldn't actually back up" in run.reply_text


def test_a_marker_shaped_focus_does_not_fail_the_plan_turn() -> None:
    """FR-DS-24: the plan reply is entirely backend-composed, so validation
    does not apply — the alternative is a user's own words failing their turn.
    The marker is still stripped from the visible reply, as every `[S#]` is."""
    sessions = SessionStore()

    plan = _turn(_discovery_graph("unused"), sessions, '/discover "what does [S1] mean", laughter')

    assert "couldn't actually back up" not in plan.reply_text
    assert "Parsed discovery:" in plan.reply_text
    assert sessions.get_or_create("s1").pending_discovery is not None


def test_a_run_records_only_the_retrieval_step_and_the_report_in_history() -> None:
    """FR-DS-28: the per-region fetches and analyses are observable in the
    log, not in the thread the next turn replays."""
    sessions = SessionStore()

    _plan_and_confirm(_discovery_graph("Joy recurs [R1]."), sessions)

    history = sessions.get_or_create("s1").history
    assert [m.name for m in history if isinstance(m, ToolMessage)] == ["query_adhoc"]
    # FR-DS-27: both turns are recorded, and each stored user message is the
    # literal text the user sent rather than a rewritten directive.
    user_messages = [str(m.content) for m in history if isinstance(m, HumanMessage)]
    assert user_messages[0] == '/discover "where joy is", laughter'
    assert user_messages[1].startswith("/discover-confirm ")


def test_a_confirmed_discovery_is_cleared_from_the_session() -> None:
    sessions = SessionStore()

    _plan_and_confirm(_discovery_graph("Joy recurs [R1]."), sessions)

    assert sessions.get_or_create("s1").pending_discovery is None


def test_a_pending_discovery_survives_an_unrelated_turn() -> None:
    sessions = SessionStore()
    graph = _discovery_graph("unused")
    _turn(graph, sessions, '/discover "where joy is", laughter')
    pending = sessions.get_or_create("s1").pending_discovery

    _turn(compile_graph(ScriptedLLM([AIMessage(content="Hello there.")]), _TOOLS), sessions, "hello")

    assert sessions.get_or_create("s1").pending_discovery is pending


def test_a_thread_reset_clears_the_pending_discovery() -> None:
    """FR-DS-08, matching `pending_query`'s existing lifecycle."""
    sessions = SessionStore()
    graph = _discovery_graph("unused")
    _turn(graph, sessions, '/discover "where joy is", laughter', ui_selection=AgentContext(sign="the-tower"))
    assert sessions.get_or_create("s1").pending_discovery is not None

    plain = compile_graph(ScriptedLLM([AIMessage(content="Hello there.")]), _TOOLS)
    _turn(plain, sessions, "hello", ui_selection=AgentContext(sign="the-magician"))

    assert sessions.get_or_create("s1").pending_discovery is None
