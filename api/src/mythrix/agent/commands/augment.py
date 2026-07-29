"""Deterministic handling of the `/augment` and `/augment-confirm` chat
commands (specs/interfaces/augmentation.md FR-AU-01–FR-AU-09, FR-AU-24): focus
parsing, confirmation rendering, instruction building and reply composition —
no generation model is involved at any point here, so the confirmation gate is
a property of this code rather than of model compliance (ADR-015).

Pure functions and dataclasses only. `agent/graph/nodes/augment.py` wires these
into nodes; nothing here imports LangGraph, so the parsing and rendering rules
are testable on their own."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

AUGMENT_COMMAND = "/augment"
AUGMENT_CONFIRM_COMMAND = "/augment-confirm"

SYNTAX_HELP = "Syntax: /augment <what to look for across the regions on screen>"

NO_REGIONS_MESSAGE = "There are no regions on screen to augment. Run a query first, then narrow it however you like."
NO_PASSAGE_MESSAGE = "None of those regions could be read back from the corpus."


@dataclass(frozen=True)
class PendingAugmentation:
    """A parsed augmentation awaiting confirmation, held in session state
    under a backend-generated id (FR-AU-05). Nothing has been read for it.

    `region_ids` is the snapshot taken when the augmentation was planned, not
    whatever is on screen at confirmation time (FR-AU-09) — the plan states an
    exact count, so the run must execute against the list that was counted."""

    id: str
    focus: str
    region_ids: tuple[str, ...]


@dataclass(frozen=True)
class RegionAugmentation:
    """One augmented region's reading, with the region identity the run
    labels it by. `label` is the citation marker the consolidation cites
    (FR-AU-30); `text` is the generated augmentation, already
    marker-stripped."""

    label: str
    region_id: str
    source: str
    locator: str
    text: str


def command_of(message: str) -> str | None:
    """The augmentation command `message` invokes, or `None`. Matches the
    whole head token rather than a prefix — a `startswith` test would read
    `/augment-confirm` as `/augment`."""
    head = message.strip().partition(" ")[0].lower()
    return head if head in (AUGMENT_COMMAND, AUGMENT_CONFIRM_COMMAND) else None


def _argument_of(message: str) -> str:
    return message.strip().partition(" ")[2].strip()


def parse_augment_command(message: str) -> str:
    """The focus an `/augment` command supplies (FR-AU-01), or `""` when it
    supplies none.

    Everything after the command name is the focus, verbatim: there is no term
    list to disambiguate it from, so commas, colons and quotes are ordinary
    characters rather than syntax (FR-AU-02). An empty focus is the only
    parse failure there is, which is why it is a value rather than an
    exception."""
    return _argument_of(message)


def confirm_id_of(message: str) -> str:
    """The pending-augmentation id an `/augment-confirm` command names, or
    `""`."""
    return _argument_of(message).partition(" ")[0]


def new_augmentation_id() -> str:
    return uuid4().hex[:8]


def confirm_command_for(augmentation_id: str) -> str:
    return f"{AUGMENT_CONFIRM_COMMAND} {augmentation_id}"


def region_label(rank: int) -> str:
    """The citation marker for the region at 1-based position `rank` in the
    supplied list (FR-AU-30). Numbering follows that list, so a region that
    could not be read leaves a gap rather than shifting its successors."""
    return f"[R{rank}]"


def _count(supplied: int, augmenting: int) -> str:
    if augmenting == supplied:
        return f"{supplied} region{'' if supplied == 1 else 's'}"
    return f"{augmenting} of {supplied} regions"


def consolidation_call_bound(item_count: int, group_size: int) -> int:
    """The exact number of consolidation invocations a hierarchical run
    performs for `item_count` augmentations grouped by at most `group_size`
    (FR-AU-21, ADR-016): one per batch at each level, repeated until one
    result remains. `item_count <= group_size` collapses to `1` — the same
    single call a flat run always made."""
    if item_count <= 1:
        return item_count
    calls = 0
    items = item_count
    while items > group_size:
        items = -(-items // group_size)  # batches produced this level
        calls += items
    return calls + 1


def consolidation_progress_message(level: int, rank: int, of: int) -> str:
    """The chat line marking one non-final consolidation invocation complete
    (FR-AU-41). `level` is 1-based from the leaf level up; `rank`/`of` name
    the invocation's position among its own level's batches."""
    return f"Consolidated group {rank}/{of} (pass {level})"


def render_plan(
    focus: str, supplied: int, augmenting: int, augmentation_id: str, *, consolidation_group_size: int = 8
) -> str:
    """The reply restating a parsed augmentation and naming the command that
    runs it (FR-AU-05). States both counts, which the backend knows exactly:
    the regions were supplied with the turn rather than retrieved. The
    consolidation count is likewise exact, never "up to" — the number of
    invocations a hierarchical run performs is deterministic from
    `augmenting` and `consolidation_group_size` alone (ADR-016)."""
    calls = consolidation_call_bound(augmenting, consolidation_group_size)
    return (
        f"Parsed augmentation:\n\n"
        f"Focus: {focus}\n\n"
        f"A run reads {_count(supplied, augmenting)} currently on screen, "
        f"one generation call each, plus {calls} call{'' if calls == 1 else 's'} to consolidate them.\n\n"
        f"Send `{confirm_command_for(augmentation_id)}` to run it."
    )


def confirm_augment_instruction(augmentation_id: str, focus: str, region_count: int) -> dict:
    """Carries `confirm_command` verbatim so a consumer's affordance sends the
    identical string a human would type (FR-AU-32). Declared with no binding:
    it triggers no request, so a consumer handles it in-app."""
    return {
        "type": "confirm_augment",
        "payload": {
            "augmentation_id": augmentation_id,
            "focus": focus,
            "region_count": region_count,
            "confirm_command": confirm_command_for(augmentation_id),
        },
    }


def augment_region_instruction(augmentation: RegionAugmentation) -> dict:
    """One region's reading, addressed to the region it belongs to
    (FR-AU-23). Declared with no binding: the consumer holds it against that
    region rather than issuing a request for it (FR-AU-26)."""
    return {
        "type": "augment_region",
        "payload": {
            "region_id": augmentation.region_id,
            "label": augmentation.label,
            "augmentation": augmentation.text,
        },
    }


def region_done_message(augmentation: RegionAugmentation) -> str:
    """The chat line marking one region complete (FR-AU-23) — the identity,
    not the reading, which travels to the region itself."""
    return f"Augmented {augmentation.label} {augmentation.source} — {augmentation.locator}"


def render_reply(consolidation: str, supplied: int, augmented: int) -> str:
    """The run's terminal reply (FR-AU-24): the consolidation and the count.
    The individual augmentations are not restated here — each one went to its
    own region as it was produced."""
    return f"{consolidation}\n\n---\n\nAugmented {_count(supplied, augmented)} on screen."
