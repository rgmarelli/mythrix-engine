"""Unit tests for `agent/graph/nodes/summary.py`: the `/summarize` deterministic
node (agent.md FR-AG-33–FR-AG-36)."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from mythrix.agent.graph.nodes.summary import summarize_node


@tool
def fetch_segments(source_id: str, start_ordinal: int, end_ordinal: int) -> list[dict]:
    """Fake fetch_segments mirroring the real tool's shape."""
    return [
        {"ordinal": ordinal, "locator": f"{source_id} {ordinal}", "section": None, "text": f"text {ordinal}"}
        for ordinal in range(start_ordinal, end_ordinal + 1)
    ]


@tool("fetch_segments")
def failing_fetch_segments(source_id: str, start_ordinal: int, end_ordinal: int) -> list[dict]:
    """Fake fetch_segments that always errors, mirroring a MythrixError."""
    return [{"error": f"unknown source {source_id!r}"}]


@tool
def summarize_passage(passage_text: str, concepts: list[str]) -> dict:
    """Fake summarize_passage mirroring the real tool's shape."""
    return {"summary": f"Summary of: {passage_text} ({', '.join(concepts)})"}


@tool("summarize_passage")
def failing_summarize_passage(passage_text: str, concepts: list[str]) -> dict:
    """Fake summarize_passage that always errors, mirroring a MythrixError."""
    return {"error": "model unavailable"}


_SUMMARIZE_TOOLS = [fetch_segments, summarize_passage]


def test_summarize_node_replies_deterministically_with_no_active_hotspot() -> None:
    state = {"messages": [HumanMessage(content="/summarize")], "region_id": None, "pending_query": None}

    result = summarize_node(state, _SUMMARIZE_TOOLS)

    assert "select" in result["messages"][0].content.lower()
    assert result["messages"][0].tool_calls == []
    assert result["instructions"] == []


def test_summarize_node_replies_deterministically_on_a_malformed_region_id() -> None:
    state = {"messages": [HumanMessage(content="/summarize")], "region_id": "not-a-region-id", "pending_query": None}

    result = summarize_node(state, _SUMMARIZE_TOOLS)

    assert "reselect" in result["messages"][0].content.lower()


def test_summarize_node_fetches_then_summarizes_with_no_focus_or_interpretant() -> None:
    state = {
        "messages": [HumanMessage(content="/summarize")],
        "region_id": "waite::0-1",
        "interpretant": None,
        "pending_query": None,
    }

    result = summarize_node(state, _SUMMARIZE_TOOLS)

    messages = result["messages"]
    tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
    assert [m.name for m in tool_messages] == ["fetch_segments", "summarize_passage"]
    assert "text 0" in tool_messages[0].content and "text 1" in tool_messages[0].content
    final = messages[-1]
    assert isinstance(final, AIMessage)
    assert final.content == "Summary of: text 0\n\ntext 1 ()"


def test_summarize_node_scopes_concepts_by_trailing_focus_text() -> None:
    state = {
        "messages": [HumanMessage(content="/summarize focus on redemption imagery")],
        "region_id": "waite::0-0",
        "interpretant": "fire",
        "pending_query": None,
    }

    result = summarize_node(state, _SUMMARIZE_TOOLS)

    assert "redemption imagery" in result["messages"][-1].content
    assert "fire" not in result["messages"][-1].content


def test_summarize_node_falls_back_to_the_current_interpretant() -> None:
    state = {
        "messages": [HumanMessage(content="/summarize")],
        "region_id": "waite::0-0",
        "interpretant": "fire",
        "pending_query": None,
    }

    result = summarize_node(state, _SUMMARIZE_TOOLS)

    assert "fire" in result["messages"][-1].content


def test_summarize_node_relays_a_fetch_segments_error_without_calling_summarize() -> None:
    state = {"messages": [HumanMessage(content="/summarize")], "region_id": "waite::0-1", "pending_query": None}

    result = summarize_node(state, [failing_fetch_segments, summarize_passage])

    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [m.name for m in tool_messages] == ["fetch_segments"]
    assert "unknown source" in result["messages"][-1].content


def test_summarize_node_relays_a_summarize_passage_error() -> None:
    state = {"messages": [HumanMessage(content="/summarize")], "region_id": "waite::0-1", "pending_query": None}

    result = summarize_node(state, [fetch_segments, failing_summarize_passage])

    assert result["messages"][-1].content == "model unavailable"
