# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `agent/context.py`: thread-reset detection, UI-selection
merging, deterministic backfill from tool results, and context-summary
rendering."""

from langchain_core.messages import AIMessage, ToolMessage

from mythrix.agent.context import (
    AgentContext,
    apply_ui_selection,
    backfill_from_tool_results,
    detect_thread_reset,
    render_context_summary,
)


def test_detect_thread_reset_true_on_region_change() -> None:
    previous = AgentContext(region_id="waite::0-1")
    incoming = AgentContext(region_id="waite::2-3")
    assert detect_thread_reset(previous, incoming) is True


def test_detect_thread_reset_true_on_session_scoped_field_change() -> None:
    previous = AgentContext(region_id="waite::0-1", sign="the-tower")
    incoming = AgentContext(region_id="waite::0-1", sign="the-sun")
    assert detect_thread_reset(previous, incoming) is True


def test_detect_thread_reset_false_when_nothing_relevant_changed() -> None:
    previous = AgentContext(region_id="waite::0-1", sign="the-tower", source_id="waite")
    incoming = AgentContext(region_id="waite::0-1", sign="the-tower", source_id="other")
    assert detect_thread_reset(previous, incoming) is False


def test_detect_thread_reset_false_when_both_regions_are_none() -> None:
    previous = AgentContext()
    incoming = AgentContext()
    assert detect_thread_reset(previous, incoming) is False


def test_apply_ui_selection_always_takes_incoming_region_id_even_when_none() -> None:
    previous = AgentContext(region_id="waite::0-1")
    incoming = AgentContext(region_id=None)
    merged = apply_ui_selection(previous, incoming)
    assert merged.region_id is None


def test_apply_ui_selection_preserves_session_scoped_field_when_incoming_is_none() -> None:
    """A sign the agent previously resolved from chat alone must survive a
    later turn whose UI selection carries no sign at all."""
    previous = AgentContext(sign="the-sun", tradition="rider-waite")
    incoming = AgentContext(sign=None, tradition=None, region_id=None)
    merged = apply_ui_selection(previous, incoming)
    assert merged.sign == "the-sun"
    assert merged.tradition == "rider-waite"


def test_apply_ui_selection_overwrites_session_scoped_field_when_incoming_sets_it() -> None:
    previous = AgentContext(sign="the-sun")
    incoming = AgentContext(sign="the-tower")
    merged = apply_ui_selection(previous, incoming)
    assert merged.sign == "the-tower"


def test_apply_ui_selection_always_takes_incoming_locator_even_when_none() -> None:
    """`locator` describes the same hotspot `region_id` does, so it follows
    the same all-or-nothing rule rather than the session-scoped "preserve
    when absent" rule."""
    previous = AgentContext(region_id="waite::0-1", locator="Ecclesiasticus 43:1-4")
    incoming = AgentContext(region_id=None, locator=None)
    merged = apply_ui_selection(previous, incoming)
    assert merged.locator is None


def _tool_call_and_result(name: str, args: dict, result: dict | list) -> list:
    import json

    return [
        AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "c1"}]),
        ToolMessage(content=json.dumps(result), name=name, tool_call_id="c1"),
    ]


def test_backfill_from_get_sign_result() -> None:
    context = AgentContext()
    messages = _tool_call_and_result(
        "get_sign",
        {"sign": "The Tower"},
        {"sign": "the-tower", "sign_name": "The Tower", "semiotic_system": "tarot", "tradition": "rider-waite"},
    )
    updated = backfill_from_tool_results(context, messages)
    assert updated.sign == "the-tower"
    assert updated.tradition == "rider-waite"
    assert updated.semiotic_system == "tarot"


def test_backfill_from_get_sign_needs_tradition_does_not_backfill() -> None:
    context = AgentContext()
    messages = _tool_call_and_result(
        "get_sign",
        {"sign": "The Tower"},
        {
            "needs_tradition": True,
            "sign": "the-tower",
            "sign_name": "The Tower",
            "traditions": [{"slug": "rider-waite", "name": "Rider-Waite-Smith"}],
        },
    )
    updated = backfill_from_tool_results(context, messages)
    assert updated.sign is None
    assert updated.tradition is None


def test_backfill_from_query_sign_uses_result_payload_not_call_args() -> None:
    """The model's call arguments carry the user's wording; the result carries
    what the tool actually resolved. Backfilling from the arguments is what put
    display names into an identity field (ADR-014)."""
    context = AgentContext()
    messages = _tool_call_and_result(
        "query_sign",
        {"sign": "The Tower", "tradition": "Rider-Waite-Smith"},
        {"sign": "the-tower", "tradition": "rider-waite", "regions": []},
    )
    updated = backfill_from_tool_results(context, messages)
    assert updated.sign == "the-tower"
    assert updated.tradition == "rider-waite"


def test_backfill_ignores_error_payloads() -> None:
    context = AgentContext(sign="the-sun")
    messages = _tool_call_and_result("get_sign", {"sign": "nope"}, {"error": "unknown sign 'nope'"})
    updated = backfill_from_tool_results(context, messages)
    assert updated.sign == "the-sun"


def test_backfill_from_list_tools_never_backfills() -> None:
    context = AgentContext(sign="the-sun")
    messages = [
        AIMessage(content="", tool_calls=[{"name": "list_signs", "args": {}, "id": "c1"}]),
        ToolMessage(content="[]", name="list_signs", tool_call_id="c1"),
    ]
    updated = backfill_from_tool_results(context, messages)
    assert updated.sign == "the-sun"


def test_backfill_from_fetch_segments_never_backfills_sign_or_tradition() -> None:
    context = AgentContext(sign="the-sun")
    messages = _tool_call_and_result(
        "fetch_segments",
        {"source_id": "waite", "start_ordinal": 0, "end_ordinal": 1},
        [{"ordinal": 0, "locator": "1", "section": "", "text": "hi"}],
    )
    updated = backfill_from_tool_results(context, messages)
    assert updated.sign == "the-sun"


def test_render_context_summary_includes_region_and_sign() -> None:
    context = AgentContext(region_id="waite::0-1", sign="the-tower", tradition="rider-waite")
    summary = render_context_summary(context)
    assert "waite::0-1" in summary
    assert "the-tower" in summary
    assert "rider-waite" in summary


def test_render_context_summary_includes_locator_when_present() -> None:
    context = AgentContext(region_id="waite::0-1", locator="Ecclesiasticus 43:1-4")
    summary = render_context_summary(context)
    assert "waite::0-1" in summary
    assert "Ecclesiasticus 43:1-4" in summary


def test_render_context_summary_omits_locator_when_absent() -> None:
    summary = render_context_summary(AgentContext(region_id="waite::0-1"))
    assert "Ecclesiasticus" not in summary


def test_render_context_summary_empty_when_nothing_set() -> None:
    assert render_context_summary(AgentContext()) == ""
