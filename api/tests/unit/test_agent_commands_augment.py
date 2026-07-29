"""Unit tests for `agent/commands/augment.py` — parsing, labelling and
rendering, with no graph and no model involved."""

from mythrix.agent.commands.augment import (
    AUGMENT_COMMAND,
    AUGMENT_CONFIRM_COMMAND,
    RegionAugmentation,
    augment_region_instruction,
    command_of,
    confirm_augment_instruction,
    confirm_command_for,
    confirm_id_of,
    consolidation_call_bound,
    consolidation_progress_message,
    new_augmentation_id,
    parse_augment_command,
    region_done_message,
    region_label,
    render_plan,
    render_reply,
)


def _augmentation(rank: int = 1, text: str = "a reading") -> RegionAugmentation:
    return RegionAugmentation(
        label=region_label(rank),
        region_id="en_drb::1841-1844",
        source="Douay-Rheims",
        locator="Genesis 21:5–8",
        text=text,
    )


def test_command_of_matches_the_whole_head_token() -> None:
    """A `startswith` test would read `/augment-confirm` as `/augment` and
    send a confirmation to the planning node."""
    assert command_of("/augment how is grief framed") == AUGMENT_COMMAND
    assert command_of("/augment-confirm 7f3a1c9e") == AUGMENT_CONFIRM_COMMAND
    assert command_of("  /AUGMENT  spacing  ") == AUGMENT_COMMAND
    assert command_of("/augmentation of things") is None
    assert command_of("what does /augment do") is None
    assert command_of("hello") is None


def test_the_focus_is_everything_after_the_command_name() -> None:
    assert parse_augment_command("/augment how is grief framed") == "how is grief framed"
    assert parse_augment_command("/augment    padded   focus  ") == "padded   focus"


def test_the_focus_is_taken_verbatim_with_no_term_syntax() -> None:
    """FR-AU-02: there is no term list to disambiguate from, so commas,
    colons, directive-shaped suffixes and quotes are ordinary characters."""
    focus = '"joy", laughter:exact, child:filter — where does it turn?'

    assert parse_augment_command(f"/augment {focus}") == focus


def test_an_absent_focus_parses_to_empty_rather_than_raising() -> None:
    """The only parse failure there is, so it is a value the node checks —
    not an exception class invented for one case."""
    assert parse_augment_command("/augment") == ""
    assert parse_augment_command("/augment    ") == ""


def test_confirm_id_is_the_first_token_of_the_argument() -> None:
    assert confirm_id_of("/augment-confirm 7f3a1c9e") == "7f3a1c9e"
    assert confirm_id_of("/augment-confirm 7f3a1c9e and more") == "7f3a1c9e"
    assert confirm_id_of("/augment-confirm") == ""


def test_a_new_id_is_not_guessable_from_the_command() -> None:
    assert new_augmentation_id() != new_augmentation_id()
    assert confirm_command_for("7f3a1c9e") == "/augment-confirm 7f3a1c9e"


def test_region_labels_follow_the_supplied_position_so_a_skip_leaves_a_gap() -> None:
    """FR-AU-30: a region that could not be read takes no label, and the ones
    after it keep the numbers their positions give them."""
    assert [region_label(rank) for rank in (1, 3, 4)] == ["[R1]", "[R3]", "[R4]"]


def test_the_plan_states_both_counts_when_the_bound_truncates() -> None:
    plan = render_plan("how is grief framed", supplied=14, augmenting=8, augmentation_id="7f3a1c")

    assert "8 of 14 regions" in plan
    assert "how is grief framed" in plan
    assert "/augment-confirm 7f3a1c" in plan


def test_the_plan_states_one_count_when_nothing_is_truncated() -> None:
    """FR-AU-05: the backend knows the exact number, because the regions came
    with the turn rather than being retrieved — so it never says "up to"."""
    plan = render_plan("focus", supplied=6, augmenting=6, augmentation_id="7f3a1c")

    assert "6 regions" in plan
    assert "of 6" not in plan
    assert "up to" not in plan


def test_the_plan_says_region_singular_for_one() -> None:
    assert "1 region " in render_plan("focus", supplied=1, augmenting=1, augmentation_id="a")


def test_the_plan_states_one_consolidation_call_when_augmenting_fits_one_group() -> None:
    """ADR-016: augmenting <= consolidation_group_size collapses to the flat,
    single-call behavior a run always had."""
    plan = render_plan("focus", supplied=6, augmenting=6, augmentation_id="7f3a1c", consolidation_group_size=8)

    assert "plus 1 call to consolidate them" in plan
    assert "up to" not in plan


def test_the_plan_states_the_exact_consolidation_call_count_for_a_large_run() -> None:
    """FR-AU-40/ADR-016: a run whose augmentations exceed the group size states
    the deterministic, multi-invocation count — still never hedged as "up to"."""
    plan = render_plan("focus", supplied=20, augmenting=20, augmentation_id="7f3a1c", consolidation_group_size=8)

    assert f"plus {consolidation_call_bound(20, 8)} calls to consolidate them" in plan
    assert "up to" not in plan


def test_consolidation_call_bound_collapses_to_one_at_or_under_the_group_size() -> None:
    assert consolidation_call_bound(1, 8) == 1
    assert consolidation_call_bound(8, 8) == 1


def test_consolidation_call_bound_grows_hierarchically_above_the_group_size() -> None:
    # 9 items, group size 8: one leaf batch of 8 + one of 1 (2 calls),
    # then 1 final call over the 2 results.
    assert consolidation_call_bound(9, 8) == 3
    # 20 items, group size 8: three leaf batches (8, 8, 4) -> 3 calls,
    # then 1 final call over the 3 results.
    assert consolidation_call_bound(20, 8) == 4
    # 65 items, group size 8: 9 leaf batches -> 9 calls, then 2 rollup
    # batches (8, 1) -> 2 calls, then 1 final call over the 2 results.
    assert consolidation_call_bound(65, 8) == 12


def test_consolidation_progress_message_names_the_group_and_pass() -> None:
    assert consolidation_progress_message(1, 2, 3) == "Consolidated group 2/3 (pass 1)"


def test_the_reply_carries_the_consolidation_and_the_count_but_not_the_readings() -> None:
    """FR-AU-24: each reading went to its own region as it was produced, so
    restating them here would duplicate them in the panel."""
    reply = render_reply("Joy recurs as reversal [R1][R3].", supplied=9, augmented=8)

    assert reply.startswith("Joy recurs as reversal [R1][R3].")
    assert "8 of 9 regions" in reply


def test_the_confirmation_instruction_carries_the_command_verbatim() -> None:
    instruction = confirm_augment_instruction("7f3a1c", "how is grief framed", 6)

    assert instruction["type"] == "confirm_augment"
    assert instruction["payload"]["confirm_command"] == "/augment-confirm 7f3a1c"
    assert instruction["payload"]["region_count"] == 6
    assert instruction["payload"]["focus"] == "how is grief framed"


def test_the_region_instruction_addresses_the_region_it_belongs_to() -> None:
    instruction = augment_region_instruction(_augmentation(text="Sara laughs."))

    assert instruction["type"] == "augment_region"
    assert instruction["payload"] == {
        "region_id": "en_drb::1841-1844",
        "label": "[R1]",
        "augmentation": "Sara laughs.",
    }


def test_the_per_region_chat_line_names_the_region_not_the_reading() -> None:
    """The reading travels to the region; the chat line is progress."""
    message = region_done_message(_augmentation(rank=2, text="a long reading nobody wants twice"))

    assert message == "Augmented [R2] Douay-Rheims — Genesis 21:5–8"
    assert "long reading" not in message
