"""Deterministic nodes for the `/augment` and `/augment-confirm` commands
(specs/interfaces/augmentation.md FR-AU-05–FR-AU-25, FR-AU-39–FR-AU-41,
ADR-012, ADR-015, ADR-016).

`plan_augment_node` parses and snapshots; `run_augment_node` executes the whole
sequence — read each region, augment each passage, consolidate — in code. The
orchestration model is invoked at no point in either turn. The model calls are
the N generation calls inside `augment_passage`, one per region, plus a
deterministic-but-variable number of further calls that consolidate them
hierarchically (`_consolidate`, ADR-016) — each of which is still one prompt
producing one string over the narrow `ChatClient`.
"""

from __future__ import annotations

import itertools
import json
import logging
import time

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.config import get_stream_writer

from mythrix.agent.citations import strip_all_markers, strip_markers
from mythrix.agent.commands.augment import (
    AUGMENT_COMMAND,
    AUGMENT_CONFIRM_COMMAND,
    NO_PASSAGE_MESSAGE,
    NO_REGIONS_MESSAGE,
    SYNTAX_HELP,
    PendingAugmentation,
    RegionAugmentation,
    augment_region_instruction,
    confirm_augment_instruction,
    confirm_id_of,
    consolidation_progress_message,
    new_augmentation_id,
    parse_augment_command,
    region_done_message,
    region_label,
    render_plan,
    render_reply,
)
from mythrix.agent.graph.state import AgentState
from mythrix.core.logging_config import truncate

logger = logging.getLogger(__name__)

_RECORD_CALL_ID = "augment-regions"


def _tool_by_name(tools: list, name: str):  # noqa: ANN001, ANN201 - BaseTool, no shared base type worth importing
    return next(t for t in tools if t.name == name)


def _backend_reply(text: str, pending: PendingAugmentation | None, messages: list | None = None) -> dict:
    """A reply composed entirely by this node, with no model-authored text in
    it — exempt from citation validation (FR-AU-31), so a marker-shaped
    sequence a user typed into a focus or an id cannot fail the turn."""
    return {
        "messages": [*(messages or []), AIMessage(content=text)],
        "pending_augmentation": pending,
        "instructions": [],
        "backend_authored": True,
    }


def plan_augment_node(state: AgentState, *, max_regions: int, consolidation_group_size: int) -> dict:
    """Parses an `/augment` command and snapshots the consumer's visible
    regions alongside it (FR-AU-05, FR-AU-09), replying with the plan and the
    command that runs it. Reads nothing and invokes no model (FR-AU-06). A
    rejected command drops any prior pending augmentation so "at most one
    outstanding" stays unambiguous (FR-AU-08), and emits no instruction."""
    focus = parse_augment_command(str(state["messages"][-1].content))
    if not focus:
        return _backend_reply(f"An augmentation needs something to look for. {SYNTAX_HELP}", None)

    region_ids = tuple(state.get("visible_regions") or ())
    if not region_ids:
        return _backend_reply(NO_REGIONS_MESSAGE, None)

    augmentation_id = new_augmentation_id()
    augmenting = min(len(region_ids), max_regions)
    logger.info(
        "augment plan: id=%s focus=%s supplied=%d augmenting=%d",
        augmentation_id,
        truncate(focus),
        len(region_ids),
        augmenting,
    )
    plan = render_plan(
        focus, len(region_ids), augmenting, augmentation_id, consolidation_group_size=consolidation_group_size
    )
    return {
        **_backend_reply(plan, None),
        "pending_augmentation": PendingAugmentation(id=augmentation_id, focus=focus, region_ids=region_ids),
        "instructions": [confirm_augment_instruction(augmentation_id, focus, augmenting)],
    }


def _record_messages(augmentations: tuple[RegionAugmentation, ...]) -> list:
    """The one fabricated tool-call pair a run records (FR-AU-35, ADR-015):
    the regions it augmented, which is what citation-marker accounting counts
    `[R#]` from. The per-region reads and generations are logged, not recorded
    — fabricating them would push a run's passages into the thread the next
    turn replays into a bounded context. Carries no passage text (FR-AU-36)."""
    payload = {
        "regions": [
            {"region_id": a.region_id, "label": a.label, "source": a.source, "locator": a.locator}
            for a in augmentations
        ]
    }
    return [
        AIMessage(content="", tool_calls=[{"name": "augment_regions", "args": {}, "id": _RECORD_CALL_ID}]),
        ToolMessage(content=json.dumps(payload), name="augment_regions", tool_call_id=_RECORD_CALL_ID),
    ]


def _consolidate(
    tools: list,  # noqa: ANN001 - BaseTool list
    focus: str,
    augmentations: tuple[RegionAugmentation, ...],
    group_size: int,
) -> tuple[dict, int]:
    """Hierarchical map-reduce over `augmentations`' readings (ADR-016):
    batches of at most `group_size` are consolidated by one generation call
    each; while more than `group_size` results remain, the results are
    themselves batched and consolidated again, until exactly one remains.
    Returns the final tool result and the number of consolidation calls made
    — N + this count is the run's total (FR-AU-21).

    The first level (raw, individually labeled augmentations) always goes
    through `consolidate_augmentations`; every level above it (already-
    synthesized text that already embeds `[R#]` markers, with no label of its
    own) goes through `rollup_augmentations` instead (FR-AU-39) — never the
    reverse, since only the first level's prompt is given a label vocabulary
    to cite from. `rollup_augmentations` is looked up only once the loop
    proves it is needed, so a run that never exceeds `group_size` costs no
    lookup and requires no such tool to be registered."""
    writer = get_stream_writer()
    consolidate = _tool_by_name(tools, "consolidate_augmentations")
    items: list[str] = [a.text for a in augmentations]
    labels: list[str] = [f"{a.label} {a.source}, {a.locator}" for a in augmentations]
    calls = 0
    level = 1

    while len(items) > group_size:
        rollup = _tool_by_name(tools, "rollup_augmentations")
        index_batches = list(itertools.batched(range(len(items)), group_size))
        next_items: list[str] = []
        for rank, idx_batch in enumerate(index_batches, start=1):
            calls += 1
            batch = [items[i] for i in idx_batch]
            if level == 1:
                label_batch = [labels[i] for i in idx_batch]
                result = consolidate.invoke(
                    {
                        "focus": focus,
                        "augmentations": [
                            {"label": lbl, "augmentation": txt} for lbl, txt in zip(label_batch, batch, strict=True)
                        ],
                    }
                )
            else:
                result = rollup.invoke({"focus": focus, "summaries": batch})
            if "error" in result:
                return result, calls
            next_items.append(result["consolidation"])
            writer({"message": consolidation_progress_message(level, rank, len(index_batches))})
        items, labels, level = next_items, [], level + 1

    calls += 1
    if level == 1:
        final = consolidate.invoke(
            {
                "focus": focus,
                "augmentations": [{"label": lbl, "augmentation": txt} for lbl, txt in zip(labels, items, strict=True)],
            }
        )
    else:
        final = _tool_by_name(tools, "rollup_augmentations").invoke({"focus": focus, "summaries": items})
    return final, calls


def run_augment_node(  # noqa: ANN001 - BaseTool list
    state: AgentState, tools: list, *, max_regions: int, consolidation_group_size: int
) -> dict:
    """Runs a confirmed augmentation (FR-AU-07, FR-AU-13–FR-AU-25).

    Which operations run and in what order is decided here, not by the
    orchestration model's tool selection: one `read_region`/`augment_passage`
    pair per region in the supplied order, then a hierarchical consolidation
    (`_consolidate`, ADR-016). The set of regions read and the order they are
    read in are exactly the snapshot taken at plan time, head-truncated to
    `max_regions` — no model participates in selecting or re-ordering one
    (FR-AU-13).

    Each completed region is streamed out as it lands (FR-AU-23) before the
    run continues, so a long run is legible while it is still running."""
    pending = state.get("pending_augmentation")
    augmentation_id = confirm_id_of(str(state["messages"][-1].content))
    if not augmentation_id:
        return _backend_reply(f"Name the augmentation to confirm, e.g. `{AUGMENT_CONFIRM_COMMAND} 7f3a1c9e`.", pending)
    if pending is None or pending.id != augmentation_id:
        return _backend_reply(
            f"No pending augmentation with id {augmentation_id!r}. "
            f"Send `{AUGMENT_COMMAND} <what to look for>` to start one.",
            pending,
        )

    started = time.monotonic()
    region_ids = pending.region_ids[:max_regions]
    logger.info(
        "augment run: id=%s focus=%s supplied=%d augmenting=%d",
        augmentation_id,
        truncate(pending.focus),
        len(pending.region_ids),
        len(region_ids),
    )

    augmentations = _augment_regions(tools, region_ids, pending)
    if not augmentations:
        logger.info("augment run: id=%s no region could be read back", augmentation_id)
        return _backend_reply(NO_PASSAGE_MESSAGE, None)

    logger.info("augment consolidate: id=%s augmentations=%d", augmentation_id, len(augmentations))
    consolidation, consolidation_calls = _consolidate(tools, pending.focus, augmentations, consolidation_group_size)
    if "error" in consolidation:
        logger.info("augment run failed: id=%s error=%s", augmentation_id, consolidation["error"])
        return _backend_reply(consolidation["error"], None)

    logger.info(
        "augment done: id=%s regions=%d model_calls=%d elapsed=%.1fs",
        augmentation_id,
        len(augmentations),
        len(augmentations) + consolidation_calls,
        time.monotonic() - started,
    )
    reply = render_reply(strip_markers(consolidation["consolidation"]), len(pending.region_ids), len(augmentations))
    return {
        "messages": [*_record_messages(augmentations), AIMessage(content=reply)],
        "pending_augmentation": None,
        "instructions": [augment_region_instruction(a) for a in augmentations],
        "backend_authored": False,
    }


def _augment_regions(
    tools: list,  # noqa: ANN001 - BaseTool list
    region_ids: tuple[str, ...],
    pending: PendingAugmentation,
) -> tuple[RegionAugmentation, ...]:
    """One augmentation per region, in the supplied order, one generation call
    each (FR-AU-19). A region whose passage cannot be read is skipped rather
    than augmented, so it costs no model call and takes no label — labels
    follow the supplied position, so a skipped region leaves a gap instead of
    shifting the ones after it (FR-AU-16)."""
    writer = get_stream_writer()
    augmentations: list[RegionAugmentation] = []
    total = len(region_ids)

    for rank, region_id in enumerate(region_ids, start=1):
        label = region_label(rank)
        started = time.monotonic()
        region = _tool_by_name(tools, "read_region").invoke({"region_id": region_id})
        if "error" in region:
            logger.info("augment region %d/%d skipped: label=%s error=%s", rank, total, label, region["error"])
            continue

        logger.info(
            "augment region %d/%d start: label=%s source=%s locator=%s",
            rank,
            total,
            label,
            region["source_id"],
            region["locator"],
        )
        result = _tool_by_name(tools, "augment_passage").invoke(
            {"passage_text": region["text"], "focus": pending.focus}
        )
        if "error" in result:
            logger.info("augment region %d/%d failed: label=%s error=%s", rank, total, label, result["error"])
            continue

        # FR-AU-31: the augmentation prompt is given no marker vocabulary, so
        # marker-shaped text here names nothing — and a region marker left in
        # place would reach the consumer claiming a citation it cannot back.
        augmentation = RegionAugmentation(
            label=label,
            region_id=region_id,
            source=region["source"],
            locator=region["locator"],
            text=strip_all_markers(result["augmentation"]).strip(),
        )
        augmentations.append(augmentation)

        writer({"message": region_done_message(augmentation)})
        writer({"instruction": augment_region_instruction(augmentation)})
        logger.info(
            "augment region %d/%d done: label=%s elapsed=%.1fs chars=%d",
            rank,
            total,
            label,
            time.monotonic() - started,
            len(augmentation.text),
        )
    return tuple(augmentations)
