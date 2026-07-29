"""Unit tests for `agent/commands/discover.py`: the two-input parse
(FR-DS-01–FR-DS-03) and the two backend-composed renderings
(FR-DS-05, FR-DS-20)."""

import re

import pytest

from mythrix.agent.commands.discover import (
    DISCOVER_COMMAND,
    DISCOVER_CONFIRM_COMMAND,
    RegionFinding,
    command_of,
    confirm_discovery_instruction,
    confirm_id_of,
    new_discovery_id,
    parse_discover_command,
    region_label,
    render_plan,
    render_report,
)
from mythrix.core.errors import AdhocQueryValidationError
from mythrix.core.models import AdhocTerm


def test_command_of_matches_the_whole_head_token() -> None:
    assert command_of('/discover "joy", laughter') == DISCOVER_COMMAND
    assert command_of("/discover-confirm 7f3a1c") == DISCOVER_CONFIRM_COMMAND
    assert command_of('  /DISCOVER "joy", laughter  ') == DISCOVER_COMMAND
    assert command_of("/discovered") is None
    assert command_of("/discover-confirmed 7f3a1c") is None
    assert command_of("tell me about The Tower") is None


def test_parse_splits_the_quoted_focus_from_the_term_list() -> None:
    focus, terms = parse_discover_command('/discover "segments where sentiment is joy", laughter, hundred:exact')

    assert focus == "segments where sentiment is joy"
    assert terms == (AdhocTerm(value="laughter"), AdhocTerm(value="hundred", directive="exact"))


def test_focus_may_contain_commas_colons_and_directive_suffixes() -> None:
    """FR-DS-03: the quotes are what delimit the focus, so nothing inside them
    is parsed as a term."""
    focus, terms = parse_discover_command('/discover "joy, grief: what:exact accompanies each", laughter')

    assert focus == "joy, grief: what:exact accompanies each"
    assert terms == (AdhocTerm(value="laughter"),)


def test_terms_parse_without_a_separating_comma_after_the_focus() -> None:
    focus, terms = parse_discover_command('/discover "joy" laughter, mirth')

    assert focus == "joy"
    assert terms == (AdhocTerm(value="laughter"), AdhocTerm(value="mirth"))


@pytest.mark.parametrize(
    "message",
    [
        "/discover joy, laughter",
        '/discover "joy, laughter',
        '/discover "", laughter',
        '/discover "   ", laughter',
        '/discover "joy"',
        '/discover "joy",',
        "/discover",
    ],
    ids=["no-quotes", "unterminated", "empty-focus", "blank-focus", "no-terms", "empty-term-list", "no-argument"],
)
def test_every_malformed_command_is_rejected_naming_the_syntax(message: str) -> None:
    """FR-DS-02: rejected without retrieving anything or invoking a model —
    this function is the whole of that path."""
    with pytest.raises(AdhocQueryValidationError) as excinfo:
        parse_discover_command(message)

    assert "/discover" in str(excinfo.value)


def test_an_unknown_directive_is_rejected_by_the_shared_term_rules() -> None:
    with pytest.raises(AdhocQueryValidationError) as excinfo:
        parse_discover_command('/discover "joy", laughter:fuzzy')

    assert "unknown directive" in str(excinfo.value)


def test_confirm_id_of_reads_the_first_argument_token() -> None:
    assert confirm_id_of("/discover-confirm 7f3a1c") == "7f3a1c"
    assert confirm_id_of("/discover-confirm 7f3a1c extra") == "7f3a1c"
    assert confirm_id_of("/discover-confirm") == ""


def test_new_discovery_id_is_short_and_unique() -> None:
    first, second = new_discovery_id(), new_discovery_id()

    assert first != second
    assert len(first) == 8


def test_plan_restates_both_inputs_the_bound_and_the_command_that_runs_it() -> None:
    plan = render_plan(
        "where joy is spoken of",
        (AdhocTerm(value="laughter"), AdhocTerm(value="hundred", directive="exact")),
        max_regions=8,
        discovery_id="7f3a1c",
    )

    assert "where joy is spoken of" in plan
    assert "- laughter" in plan
    assert "- hundred [exact]" in plan
    assert "up to 8" in plan
    assert "`/discover-confirm 7f3a1c`" in plan


def test_plan_states_the_bound_not_a_retrieved_count() -> None:
    """FR-DS-06: nothing has been retrieved when this renders, so the only
    quantity the plan can state is the bound itself."""
    plan = render_plan("joy", (AdhocTerm(value="laughter"),), max_regions=8, discovery_id="7f3a1c")

    counts = re.findall(r"\d+", plan.replace("7f3a1c", ""))
    assert counts == ["8"]


def test_report_leads_with_the_consolidation_then_one_section_per_region() -> None:
    findings = (
        RegionFinding(region_label(1), "Douay-Rheims", "Genesis 21:6", 1, 0.8123, "Sara laughs."),
        RegionFinding(region_label(2), "Douay-Rheims", "Luke 6:21", 2, 0.7011, "Weeping turns to laughter."),
    )

    report = render_report("where joy is spoken of", 34, findings, "Joy recurs as reversal [R1][R2].")

    assert report.index("Joy recurs as reversal") < report.index("### [R1]")
    assert "Read 2 of 34 matching region(s)." in report
    assert "### [R1] Douay-Rheims — Genesis 21:6" in report
    assert "rank 1 · score 0.812" in report
    assert "Sara laughs." in report
    assert "### [R2] Douay-Rheims — Luke 6:21" in report


def test_report_labels_by_retrieval_rank_so_an_unread_region_leaves_a_gap() -> None:
    findings = (
        RegionFinding(region_label(1), "Douay-Rheims", "Genesis 21:6", 1, 0.8, "Sara laughs."),
        RegionFinding(region_label(3), "Douay-Rheims", "Luke 6:21", 3, 0.7, "Weeping turns."),
    )

    report = render_report("joy", 34, findings, "Joy recurs [R1][R3].")

    assert "### [R1]" in report
    assert "### [R2]" not in report
    assert "### [R3]" in report


def test_confirm_instruction_carries_the_command_verbatim_and_both_inputs() -> None:
    """FR-DS-31: the affordance sends the identical string a human would type,
    so the chip and the typed command are one path, not two."""
    instruction = confirm_discovery_instruction(
        "7f3a1c", "where joy is", (AdhocTerm(value="laughter"), AdhocTerm(value="hundred", directive="exact"))
    )

    assert instruction["type"] == "confirm_discovery"
    assert instruction["payload"]["confirm_command"] == "/discover-confirm 7f3a1c"
    assert instruction["payload"]["discovery_id"] == "7f3a1c"
    assert instruction["payload"]["focus"] == "where joy is"
    assert instruction["payload"]["terms"] == [
        {"value": "laughter", "directive": None},
        {"value": "hundred", "directive": "exact"},
    ]


def test_the_confirm_command_in_the_instruction_matches_the_one_in_the_plan() -> None:
    terms = (AdhocTerm(value="laughter"),)
    plan = render_plan("where joy is", terms, max_regions=8, discovery_id="7f3a1c")

    assert confirm_discovery_instruction("7f3a1c", "where joy is", terms)["payload"]["confirm_command"] in plan
