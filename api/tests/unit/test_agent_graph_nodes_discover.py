"""Unit tests for `agent/graph/nodes/discover.py`: the two deterministic
discovery nodes (discovery.md FR-DS-05–FR-DS-21, ADR-015). Fake tools stand in
for the real ones, so the operation sequence and the generation-call count are
directly observable with no Ollama involved."""

import json
import logging

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from mythrix.agent.commands.discover import PendingDiscovery
from mythrix.agent.graph.nodes.discover import plan_discovery_node, run_discovery_node
from mythrix.core.models import AdhocTerm

_PENDING = PendingDiscovery(
    id="7f3a1c",
    focus="where joy is spoken of",
    terms=(AdhocTerm(value="laughter"), AdhocTerm(value="hundred", directive="exact")),
)


class Calls:
    """Records every tool invocation in order, so a test can assert the
    sequence the node decided on rather than its own expectations of it."""

    def __init__(self) -> None:
        self.names: list[str] = []
        self.generation_calls = 0


def _tools(calls: Calls, *, region_count: int = 3, matched_count: int = 34, unreadable: set[int] = frozenset()):
    @tool
    def query_adhoc(terms: list[dict], limit: int) -> dict:
        """Fake query_adhoc mirroring the real tool's shape."""
        calls.names.append("query_adhoc")
        return {
            "matched_count": matched_count,
            "regions": [
                {
                    "region_id": f"waite::{i * 10}-{i * 10 + 2}",
                    "source": "Douay-Rheims",
                    "source_id": "waite",
                    "locator": f"Genesis {i + 1}:1-3",
                    "score": 0.9 - i / 100,
                    "convergence_count": 2,
                    "matches": [],
                }
                for i in range(region_count)
            ][:limit],
        }

    @tool
    def fetch_segments(source_id: str, start_ordinal: int, end_ordinal: int) -> list[dict]:
        """Fake fetch_segments mirroring the real tool's shape."""
        calls.names.append("fetch_segments")
        if start_ordinal // 10 in unreadable:
            return [{"error": f"unknown source {source_id!r}"}]
        return [
            {"ordinal": o, "locator": f"{source_id} {o}", "section": None, "text": f"text {o}"}
            for o in range(start_ordinal, end_ordinal + 1)
        ]

    @tool
    def analyze_passage(passage_text: str, focus: str, concepts: list[str]) -> dict:
        """Fake analyze_passage mirroring the real tool's shape."""
        calls.names.append("analyze_passage")
        calls.generation_calls += 1
        return {"finding": f"finding on {passage_text.splitlines()[0]}"}

    @tool
    def consolidate_findings(focus: str, findings: list[dict], concepts: list[str]) -> dict:
        """Fake consolidate_findings mirroring the real tool's shape."""
        calls.names.append("consolidate_findings")
        calls.generation_calls += 1
        labels = "".join(finding["label"].split(" ")[0] for finding in findings)
        return {"consolidation": f"Joy recurs {labels}."}

    return [query_adhoc, fetch_segments, analyze_passage, consolidate_findings]


def _run(tools: list, pending: PendingDiscovery | None = _PENDING, message: str = "/discover-confirm 7f3a1c", **kw):
    state = {"messages": [HumanMessage(content=message)], "pending_discovery": pending}
    return run_discovery_node(state, tools, max_regions=kw.pop("max_regions", 8))


# --- planning -------------------------------------------------------------


def test_plan_holds_both_inputs_and_retrieves_nothing() -> None:
    """FR-DS-05, FR-DS-06: the plan turn parses and holds. The node is given
    no tools at all, so it could not retrieve if it tried."""
    state = {"messages": [HumanMessage(content='/discover "where joy is", laughter, hundred:exact')]}

    result = plan_discovery_node(state, max_regions=8)

    pending = result["pending_discovery"]
    assert pending.focus == "where joy is"
    assert pending.terms == (AdhocTerm(value="laughter"), AdhocTerm(value="hundred", directive="exact"))
    assert f"/discover-confirm {pending.id}" in result["messages"][-1].content
    assert result["backend_authored"] is True


def test_a_malformed_plan_drops_any_outstanding_discovery() -> None:
    """FR-DS-08: "at most one outstanding" stays unambiguous — a failed parse
    leaves nothing behind to confirm."""
    state = {"messages": [HumanMessage(content="/discover joy, laughter")], "pending_discovery": _PENDING}

    result = plan_discovery_node(state, max_regions=8)

    assert result["pending_discovery"] is None
    assert "Couldn't parse" in result["messages"][-1].content


def test_a_marker_shaped_focus_cannot_fail_the_plan_turn() -> None:
    """FR-DS-24: the plan reply is entirely backend-composed, so it is exempt
    from citation validation — which is what stops this echo from failing."""
    state = {"messages": [HumanMessage(content='/discover "what does [S1] mean", laughter')]}

    result = plan_discovery_node(state, max_regions=8)

    assert "[S1]" in result["messages"][-1].content
    assert result["backend_authored"] is True


# --- the confirmation gate ------------------------------------------------


def test_an_unmatched_id_runs_nothing_and_preserves_the_pending_discovery() -> None:
    """FR-DS-07, and the typo case: a mistyped id must not destroy the plan."""
    calls = Calls()

    result = _run(_tools(calls), message="/discover-confirm deadbeef")

    assert calls.names == []
    assert result["pending_discovery"] is _PENDING
    assert result["backend_authored"] is True


def test_confirming_with_no_outstanding_discovery_runs_nothing() -> None:
    calls = Calls()

    result = _run(_tools(calls), pending=None)

    assert calls.names == []
    assert "No pending discovery" in result["messages"][-1].content


def test_a_confirmation_naming_no_id_runs_nothing() -> None:
    calls = Calls()

    result = _run(_tools(calls), message="/discover-confirm")

    assert calls.names == []
    assert "Name the discovery" in result["messages"][-1].content


def test_a_marker_shaped_id_cannot_fail_the_turn() -> None:
    result = _run(_tools(Calls()), message="/discover-confirm [R9]")

    assert "[R9]" in result["messages"][-1].content
    assert result["backend_authored"] is True


# --- the run -------------------------------------------------------------


def test_the_run_calls_its_tools_in_one_fixed_order() -> None:
    """FR-DS-09: retrieve, then fetch-and-read each region, then consolidate —
    decided here, not by a model's tool selection."""
    calls = Calls()

    _run(_tools(calls, region_count=2))

    assert calls.names == [
        "query_adhoc",
        "fetch_segments",
        "analyze_passage",
        "fetch_segments",
        "analyze_passage",
        "consolidate_findings",
    ]


@pytest.mark.parametrize("region_count", [1, 3, 5])
def test_a_run_invokes_the_generation_model_exactly_n_plus_one_times(region_count: int) -> None:
    """FR-DS-18: the fan-out is arithmetic in the region count, never a
    function of model behavior."""
    calls = Calls()

    _run(_tools(calls, region_count=region_count))

    assert calls.generation_calls == region_count + 1


def test_regions_are_read_and_reported_in_retrievals_own_order() -> None:
    """FR-DS-12: no model participates in selecting or re-ordering a region."""
    result = _run(_tools(Calls(), region_count=3))

    report = result["messages"][-1].content
    assert report.index("[R1] Douay-Rheims — Genesis 1:1-3") < report.index("[R2] Douay-Rheims — Genesis 2:1-3")
    assert report.index("[R2] Douay-Rheims — Genesis 2:1-3") < report.index("[R3] Douay-Rheims — Genesis 3:1-3")


def test_the_bound_is_passed_to_retrieval_and_reported_against_the_matched_count() -> None:
    """FR-DS-13: the tool truncates, so the `[R#]` ids and the report's
    sections are the same list by construction."""
    calls = Calls()

    result = _run(_tools(calls, region_count=10, matched_count=34), max_regions=2)

    assert calls.generation_calls == 3
    assert "Read 2 of 34 matching region(s)." in result["messages"][-1].content


def test_no_matching_region_ends_the_turn_without_invoking_the_model() -> None:
    """FR-DS-14."""
    calls = Calls()

    result = _run(_tools(calls, region_count=0, matched_count=0))

    assert calls.generation_calls == 0
    assert calls.names == ["query_adhoc"]
    assert result["backend_authored"] is True


def test_a_retrieval_error_ends_the_turn_without_invoking_the_model() -> None:
    @tool
    def query_adhoc(terms: list[dict], limit: int) -> dict:
        """Fake query_adhoc mirroring the real tool's shape."""
        return {"error": "model unavailable"}

    calls = Calls()
    tools = [query_adhoc, *_tools(calls)[1:]]

    result = _run(tools)

    assert calls.generation_calls == 0
    assert result["messages"][-1].content == "model unavailable"


def test_an_unreadable_region_is_skipped_without_costing_a_generation_call() -> None:
    """A region whose passage cannot be read back is not analyzed, so it takes
    no label — labels follow retrieval rank, leaving a gap rather than
    shifting the regions after it."""
    calls = Calls()

    result = _run(_tools(calls, region_count=3, unreadable={1}))

    assert calls.generation_calls == 3  # two regions read, plus the consolidation
    report = result["messages"][-1].content
    assert "### [R1]" in report
    assert "### [R2]" not in report
    assert "### [R3]" in report
    assert "Read 2 of 34 matching region(s)." in report


def test_no_readable_region_ends_the_turn_without_consolidating() -> None:
    calls = Calls()

    result = _run(_tools(calls, region_count=2, unreadable={0, 1}))

    assert calls.generation_calls == 0
    assert "consolidate_findings" not in calls.names
    assert result["backend_authored"] is True


def test_a_run_reads_each_regions_full_contiguous_range() -> None:
    """FR-DS-15: the passage is read by structural coordinate, not taken from
    the region's own match-carrying segments."""
    calls = Calls()
    passages: list[str] = []

    @tool
    def analyze_passage(passage_text: str, focus: str, concepts: list[str]) -> dict:
        """Fake analyze_passage mirroring the real tool's shape."""
        passages.append(passage_text)
        calls.generation_calls += 1
        return {"finding": "a finding"}

    tools = [*_tools(calls, region_count=1)[:2], analyze_passage, _tools(calls)[3]]
    _run(tools)

    assert passages == ["text 0\n\ntext 1\n\ntext 2"]


def test_the_analysis_receives_the_focus_and_the_terms() -> None:
    seen: list[tuple[str, list[str]]] = []
    calls = Calls()

    @tool
    def analyze_passage(passage_text: str, focus: str, concepts: list[str]) -> dict:
        """Fake analyze_passage mirroring the real tool's shape."""
        seen.append((focus, concepts))
        calls.generation_calls += 1
        return {"finding": "a finding"}

    tools = [*_tools(calls, region_count=1)[:2], analyze_passage, _tools(calls)[3]]
    _run(tools)

    assert seen == [("where joy is spoken of", ["laughter", "hundred"])]


def test_the_consolidation_receives_labels_and_findings_but_no_passage_text() -> None:
    """FR-DS-17."""
    seen: list[list[dict]] = []
    calls = Calls()

    @tool
    def analyze_passage(passage_text: str, focus: str, concepts: list[str]) -> dict:
        """Fake analyze_passage whose finding does not echo the passage, so
        passage text reaching the consolidation could only come from the node."""
        calls.generation_calls += 1
        return {"finding": "a finding"}

    @tool
    def consolidate_findings(focus: str, findings: list[dict], concepts: list[str]) -> dict:
        """Fake consolidate_findings mirroring the real tool's shape."""
        seen.append(findings)
        calls.generation_calls += 1
        return {"consolidation": "Joy recurs [R1]."}

    tools = [*_tools(calls, region_count=1)[:2], analyze_passage, consolidate_findings]
    _run(tools)

    (findings,) = seen
    assert findings[0]["label"].startswith("[R1] Douay-Rheims")
    assert findings[0]["finding"] == "a finding"
    assert "text 0" not in json.dumps(findings)


def test_marker_shaped_text_in_a_finding_is_removed_before_it_enters_the_report() -> None:
    """FR-DS-25: the analysis prompt is given no marker vocabulary, so this is
    noise — and left in place it would be validated against ids it was never
    told about."""
    calls = Calls()

    @tool
    def analyze_passage(passage_text: str, focus: str, concepts: list[str]) -> dict:
        """Fake analyze_passage mirroring the real tool's shape."""
        calls.generation_calls += 1
        return {"finding": "Sara laughs [S1] here [G2], per [R7]."}

    tools = [*_tools(calls, region_count=1)[:2], analyze_passage, _tools(calls)[3]]
    result = _run(tools)

    report = result["messages"][-1].content
    assert "[S1]" not in report
    assert "[G2]" not in report
    assert "[R7]" not in report
    assert "Sara laughs" in report


def test_history_records_only_the_retrieval_step_and_the_report() -> None:
    """FR-DS-28, ADR-015: fabricating the per-region trace would push a run's
    passages into the thread the next turn replays into a bounded context."""
    result = _run(_tools(Calls(), region_count=3))

    messages = result["messages"]
    tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
    assert [m.name for m in tool_messages] == ["query_adhoc"]
    assert isinstance(messages[-1], AIMessage)
    # The one recorded tool result carries region identity, never the
    # passages — those reached the run only through the unrecorded fetches.
    assert "text 0" not in tool_messages[0].content
    assert "segments" not in tool_messages[0].content


def test_the_fabricated_retrieval_result_mints_one_marker_id_per_reported_region() -> None:
    result = _run(_tools(Calls(), region_count=3))

    (tool_message,) = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    payload = json.loads(tool_message.content)
    assert len(payload["regions"]) == 3
    assert result["messages"][-1].content.count("### [R") == 3


def test_a_confirmed_discovery_is_cleared() -> None:
    """FR-DS-08: confirming consumes it, so the same id cannot run twice."""
    result = _run(_tools(Calls(), region_count=1))

    assert result["pending_discovery"] is None


def test_the_report_is_not_exempt_from_citation_validation() -> None:
    """FR-DS-24 is about replies with no model text in them. A report embeds
    the consolidation, so it stays subject to FR-DS-22."""
    result = _run(_tools(Calls(), region_count=1))

    assert result["backend_authored"] is False


def test_every_step_of_a_run_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """FR-DS-19: with no streaming, the log is the only visibility a run has."""
    with caplog.at_level(logging.INFO, logger="mythrix.agent.graph.nodes.discover"):
        _run(_tools(Calls(), region_count=2))

    messages = [record.getMessage() for record in caplog.records]
    assert any("discover run:" in m and "matched=34" in m and "reading=2" in m for m in messages)
    assert any("discover region 1/2 start" in m and "Genesis 1:1-3" in m for m in messages)
    assert any("discover region 1/2 done" in m and "elapsed=" in m for m in messages)
    assert any("discover region 2/2 done" in m for m in messages)
    assert any("discover consolidate:" in m and "findings=2" in m for m in messages)
    assert any("discover done:" in m and "model_calls=3" in m and "elapsed=" in m for m in messages)


def test_the_plan_turn_emits_one_confirmation_instruction() -> None:
    """FR-DS-31: what the chip is rendered from."""
    state = {"messages": [HumanMessage(content='/discover "where joy is", laughter')]}

    result = plan_discovery_node(state, max_regions=8)

    (instruction,) = result["instructions"]
    assert instruction["type"] == "confirm_discovery"
    assert instruction["payload"]["confirm_command"] == f"/discover-confirm {result['pending_discovery'].id}"


def test_a_malformed_plan_emits_no_instruction() -> None:
    state = {"messages": [HumanMessage(content="/discover joy, laughter")]}

    assert plan_discovery_node(state, max_regions=8)["instructions"] == []


def test_a_run_emits_no_instruction() -> None:
    """FR-DS-11: retrieval executes within the turn — nothing is handed to a
    consumer to run."""
    assert _run(_tools(Calls(), region_count=1))["instructions"] == []
    assert _run(_tools(Calls()), message="/discover-confirm deadbeef")["instructions"] == []
