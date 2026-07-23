"""Unit tests for `agent/turn_service.py::run_chat_turn` — drives a stub
tool-calling model through `compile_agent_graph`, no live Ollama involved."""

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from mythrix.agent.context import AgentUiSelection
from mythrix.agent.graph import compile_agent_graph
from mythrix.agent.sessions import SessionStore
from mythrix.agent.turn_service import run_chat_turn


@tool
def get_symbol(symbol: str, tradition: str | None = None) -> dict:
    """Fake get_symbol mirroring the real tool's needs_tradition shape."""
    if tradition is None:
        return {"needs_tradition": True, "symbol": "The Magician", "traditions": ["rider-waite", "marseille"]}
    return {
        "sign": "The Magician",
        "semiotic_system": "tarot",
        "tradition": tradition,
        "citations": [{"source": "Waite", "locator": "p. 1"}],
    }


_TOOLS = [get_symbol]


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


def test_normal_turn_grounds_the_reply_backfills_context_and_builds_cards() -> None:
    script = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "get_symbol", "args": {"symbol": "The Magician", "tradition": "rider-waite"}, "id": "c1"}
            ],
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
    assert len(response.cards) == 1
    assert response.cards[0].type == "citation"
    assert response.cards[0].source_label == "Waite"
    assert response.thread_reset is False


def test_hotspot_navigation_resets_the_thread_and_clears_agent_notes() -> None:
    script = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "get_symbol", "args": {"symbol": "The Magician", "tradition": "rider-waite"}, "id": "c1"}
            ],
        ),
        AIMessage(content="Noted [G1].\n```agent-notes\nalready summarized this passage\n```"),
        AIMessage(
            content="",
            tool_calls=[
                {"name": "get_symbol", "args": {"symbol": "The Magician", "tradition": "rider-waite"}, "id": "c2"}
            ],
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
    assert sessions.get_or_create("s1").agent_notes == "already summarized this passage"

    second = run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="s1",
        message="tell me about it again",
        ui_selection=AgentUiSelection(region_id="waite::2-3"),
        max_tool_iterations=8,
    )

    assert second.thread_reset is True
    assert sessions.get_or_create("s1").agent_notes == ""
    # The raw transcript the model sees must not carry over either — otherwise
    # a bad turn from the old thread keeps getting imitated in the new one.
    # One turn is HumanMessage + tool-call AIMessage + ToolMessage + final
    # AIMessage; a leaking reset would leave the first turn's 4 messages too.
    assert len(sessions.get_or_create("s1").history) == 4


def test_model_driven_reset_drops_the_stale_pre_reset_history_too() -> None:
    script = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "get_symbol", "args": {"symbol": "The Magician", "tradition": "rider-waite"}, "id": "c1"}
            ],
        ),
        AIMessage(content="First reply [G1]."),
        AIMessage(
            content="",
            tool_calls=[
                {"name": "get_symbol", "args": {"symbol": "The Magician", "tradition": "marseille"}, "id": "c2"}
            ],
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
        [AIMessage(content="", tool_calls=[{"name": "get_symbol", "args": {"symbol": "The Magician"}, "id": "c1"}])]
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
