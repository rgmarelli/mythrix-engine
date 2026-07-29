"""Deterministic nodes for the `/discover` and `/discover-confirm` commands
(specs/interfaces/discovery.md FR-DS-05–FR-DS-19, ADR-012, ADR-015).

`plan_discovery_node` parses and holds; `run_discovery_node` executes the whole
sequence — retrieve, then read each region, then consolidate — in code. The
orchestration model is invoked at no point in either turn. The only model calls
are the N+1 generation calls inside `analyze_passage`/`consolidate_findings`,
each of which is one prompt producing one string over the narrow `ChatClient`.
"""

from __future__ import annotations

import json
import logging
import time

from langchain_core.messages import AIMessage, ToolMessage

from mythrix.agent.citations import strip_all_markers, strip_markers
from mythrix.agent.commands.discover import (
    DISCOVER_COMMAND,
    DISCOVER_CONFIRM_COMMAND,
    NO_MATCH_MESSAGE,
    NO_PASSAGE_MESSAGE,
    PendingDiscovery,
    RegionFinding,
    confirm_discovery_instruction,
    confirm_id_of,
    new_discovery_id,
    parse_discover_command,
    region_label,
    render_plan,
    render_report,
)
from mythrix.agent.graph.state import AgentState
from mythrix.core.errors import AdhocQueryValidationError
from mythrix.core.logging_config import truncate
from mythrix.core.retrieval.pipeline import parse_region_id

logger = logging.getLogger(__name__)

_QUERY_CALL_ID = "discover-query"


def _tool_by_name(tools: list, name: str):  # noqa: ANN001, ANN201 - BaseTool, no shared base type worth importing
    return next(t for t in tools if t.name == name)


def _backend_reply(text: str, pending: PendingDiscovery | None, messages: list | None = None) -> dict:
    """A reply composed entirely by this node, with no model-authored text in
    it — exempt from citation validation (FR-DS-24), so a marker-shaped
    sequence a user typed into a focus or an id cannot fail the turn."""
    return {
        "messages": [*(messages or []), AIMessage(content=text)],
        "pending_discovery": pending,
        "instructions": [],
        "backend_authored": True,
    }


def plan_discovery_node(state: AgentState, *, max_regions: int) -> dict:
    """Parses a `/discover` command's two inputs and holds them pending
    confirmation (FR-DS-05), replying with the plan and the command that runs
    it. Retrieves nothing and invokes no model (FR-DS-06). A parse error drops
    any prior pending discovery so "at most one outstanding" stays unambiguous
    (FR-DS-02, FR-DS-08), and emits no instruction (FR-DS-31)."""
    try:
        focus, terms = parse_discover_command(str(state["messages"][-1].content))
    except AdhocQueryValidationError as exc:
        return _backend_reply(f"Couldn't parse that discovery: {exc}", None)

    discovery_id = new_discovery_id()
    logger.info(
        "discover plan: id=%s focus=%s terms=%s max_regions=%d",
        discovery_id,
        truncate(focus),
        [term.value for term in terms],
        max_regions,
    )
    return {
        **_backend_reply(render_plan(focus, terms, max_regions, discovery_id), None),
        "pending_discovery": PendingDiscovery(id=discovery_id, focus=focus, terms=terms),
        "instructions": [confirm_discovery_instruction(discovery_id, focus, terms)],
    }


def _query_messages(args: dict, result: dict) -> list:
    """The one fabricated tool-call pair a run records (FR-DS-28, ADR-015):
    the retrieval step, which is what citation-marker accounting counts
    `[R#]` from. The per-region fetches and analyses are logged, not recorded
    — fabricating them would push a run's eight passages into the thread the
    next turn replays into a bounded context."""
    return [
        AIMessage(content="", tool_calls=[{"name": "query_adhoc", "args": args, "id": _QUERY_CALL_ID}]),
        ToolMessage(content=json.dumps(result), name="query_adhoc", tool_call_id=_QUERY_CALL_ID),
    ]


def _passage_of(tools: list, region: dict) -> str | None:
    """One region's full contiguous ordinal range, internal gaps included,
    read verbatim by structural coordinate (FR-DS-15) — never the
    matched-only subset the region itself carries."""
    try:
        source_id, start_ordinal, end_ordinal = parse_region_id(region["region_id"])
    except ValueError:
        return None
    segments = _tool_by_name(tools, "fetch_segments").invoke(
        {"source_id": source_id, "start_ordinal": start_ordinal, "end_ordinal": end_ordinal}
    )
    if not segments or any(isinstance(segment, dict) and "error" in segment for segment in segments):
        return None
    return "\n\n".join(segment["text"] for segment in segments)


def run_discovery_node(state: AgentState, tools: list, *, max_regions: int) -> dict:  # noqa: ANN001 - BaseTool list
    """Runs a confirmed discovery (FR-DS-07, FR-DS-09–FR-DS-21).

    Which operations run and in what order is decided here, not by the
    orchestration model's tool selection: one `query_adhoc`, then one
    `fetch_segments`/`analyze_passage` pair per region in retrieval's own
    order, then one `consolidate_findings`. The set of regions read and the
    order they are read in are exactly what retrieval returned, head-truncated
    to `max_regions` — no model participates in selecting or re-ordering one
    (FR-DS-12).

    The reply is composed here from the retrieved region identities and the
    generated findings, so every locator, rank and score in it is the
    retrieved value verbatim (FR-DS-20)."""
    pending = state.get("pending_discovery")
    discovery_id = confirm_id_of(str(state["messages"][-1].content))
    if not discovery_id:
        return _backend_reply(f"Name the discovery to confirm, e.g. `{DISCOVER_CONFIRM_COMMAND} 7f3a1c9e`.", pending)
    if pending is None or pending.id != discovery_id:
        return _backend_reply(
            f"No pending discovery with id {discovery_id!r}. "
            f'Send `{DISCOVER_COMMAND} "<focus>", <terms>` to start one.',
            pending,
        )

    started = time.monotonic()
    concepts = [term.value for term in pending.terms]
    query_args = {"terms": [term.model_dump() for term in pending.terms], "limit": max_regions}
    query_result = _tool_by_name(tools, "query_adhoc").invoke(query_args)
    query_messages = _query_messages(query_args, query_result)

    if "error" in query_result:
        logger.info("discover run failed: id=%s error=%s", discovery_id, query_result["error"])
        return _backend_reply(query_result["error"], None, query_messages)

    regions = query_result["regions"]
    matched_count = query_result["matched_count"]
    logger.info(
        "discover run: id=%s focus=%s terms=%s matched=%d reading=%d",
        discovery_id,
        truncate(pending.focus),
        concepts,
        matched_count,
        len(regions),
    )
    if not regions:
        return _backend_reply(NO_MATCH_MESSAGE, None, query_messages)

    findings = _read_regions(tools, regions, pending, concepts)
    if not findings:
        logger.info("discover run: id=%s no region could be read back", discovery_id)
        return _backend_reply(NO_PASSAGE_MESSAGE, None, query_messages)

    logger.info("discover consolidate: id=%s findings=%d", discovery_id, len(findings))
    consolidation = _tool_by_name(tools, "consolidate_findings").invoke(
        {
            "focus": pending.focus,
            "findings": [{"label": f"{f.label} {f.source}, {f.locator}", "finding": f.text} for f in findings],
            "concepts": concepts,
        }
    )
    if "error" in consolidation:
        logger.info("discover run failed: id=%s error=%s", discovery_id, consolidation["error"])
        return _backend_reply(consolidation["error"], None, query_messages)

    elapsed = time.monotonic() - started
    logger.info(
        "discover done: id=%s regions=%d model_calls=%d elapsed=%.1fs",
        discovery_id,
        len(findings),
        len(findings) + 1,
        elapsed,
    )
    report = render_report(pending.focus, matched_count, findings, strip_markers(consolidation["consolidation"]))
    return {
        "messages": [*query_messages, AIMessage(content=report)],
        "pending_discovery": None,
        "instructions": [],
        "backend_authored": False,
    }


def _read_regions(
    tools: list,  # noqa: ANN001 - BaseTool list
    regions: list[dict],
    pending: PendingDiscovery,
    concepts: list[str],
) -> tuple[RegionFinding, ...]:
    """One finding per region, in retrieval's order, one generation call each
    (FR-DS-16). A region whose passage cannot be read back is skipped rather
    than analyzed, so it costs no model call and takes no label — labels
    follow retrieval rank, so a skipped region leaves a gap instead of
    shifting the ones after it."""
    findings: list[RegionFinding] = []
    for rank, region in enumerate(regions, start=1):
        label = region_label(rank)
        logger.info(
            "discover region %d/%d start: label=%s source=%s locator=%s",
            rank,
            len(regions),
            label,
            region["source_id"],
            region["locator"],
        )
        region_started = time.monotonic()
        passage = _passage_of(tools, region)
        if passage is None:
            logger.info("discover region %d/%d skipped: label=%s passage unavailable", rank, len(regions), label)
            continue

        result = _tool_by_name(tools, "analyze_passage").invoke(
            {"passage_text": passage, "focus": pending.focus, "concepts": concepts}
        )
        if "error" in result:
            logger.info("discover region %d/%d failed: label=%s error=%s", rank, len(regions), label, result["error"])
            continue

        # FR-DS-25: the analysis prompt is given no marker vocabulary, so
        # marker-shaped text here is noise, not a citation — and a region
        # marker left in place would survive into the report naming a section
        # this finding knows nothing about, failing the turn at validation.
        finding = strip_all_markers(result["finding"]).strip()
        findings.append(
            RegionFinding(
                label=label,
                source=region["source"],
                locator=region["locator"],
                rank=rank,
                score=region["score"],
                text=finding,
            )
        )
        logger.info(
            "discover region %d/%d done: label=%s elapsed=%.1fs chars=%d",
            rank,
            len(regions),
            label,
            time.monotonic() - region_started,
            len(finding),
        )
    return tuple(findings)
