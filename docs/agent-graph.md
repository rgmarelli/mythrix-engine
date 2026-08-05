# The Agent Graph

This document is a reference for the LangGraph state machine one conversational
turn runs through: every node and edge, the tool-calling loop, the post-hoc
fact-check pass, and the full `/` command vocabulary. It complements
[architecture.md §5](architecture.md#5-the-conversational-agent), which gives
the narrative version — this one is the diagram and the tables. The graph
itself is built by
[`agent/graph/builder.py::compile_agent_graph`](../api/src/mythrix/agent/graph/builder.py),
which stays the source of truth if this document and the code ever disagree.

## Contents

- [1. Graph diagram](#1-graph-diagram)
- [2. Nodes](#2-nodes)
- [3. Command dispatch](#3-command-dispatch)
- [4. The tool-calling loop](#4-the-tool-calling-loop)
- [5. Post-hoc fact-checking](#5-post-hoc-fact-checking)
- [6. Bounds and the recursion budget](#6-bounds-and-the-recursion-budget)
- [7. Turn state](#7-turn-state)
- [8. Related specs and ADRs](#8-related-specs-and-adrs)

## 1. Graph diagram

```mermaid
flowchart TB
    START([START])
    AGENT["agent\n(model call)"]
    TOOLS["tools\n(ToolNode)"]
    CLARIFY["clarify"]
    FACTCHECK["fact_check\n(model call)"]
    PARSE["parse_query"]
    EXEC["execute_query"]
    SUMMARIZE["summarize"]
    PLAN["plan_augment"]
    RUN["run_augment"]
    END_([END])

    START -- "route_input" --> AGENT
    START -- "/query" --> PARSE
    START -- "/query-confirm" --> EXEC
    START -- "/summarize" --> SUMMARIZE
    START -- "/augment" --> PLAN
    START -- "/augment-confirm" --> RUN

    PARSE --> END_
    EXEC --> END_
    SUMMARIZE --> END_
    PLAN --> END_
    RUN --> END_

    AGENT -- "tool_calls present" --> TOOLS
    AGENT -- "final answer" --> FACTCHECK
    TOOLS -- "needs_* key" --> CLARIFY
    TOOLS -- "otherwise" --> AGENT
    CLARIFY --> END_

    FACTCHECK --> END_
```

One loop remains in the graph: the **tool-calling loop** (`agent` ⇄ `tools`),
which counts toward the outer `recursion_limit` (§6). `fact_check` is a single
pass, not a loop — it never routes back to `agent` (ADR-025 superseded the
in-graph citation-retry loop this diagram used to show).

## 2. Nodes

| Node | Kind | Purpose | Source |
|---|---|---|---|
| `agent` | model call | Prepends the system prompt (+ `context_summary`) fresh every call, invokes the tool-bound model. | [`graph/nodes/llm.py::agent_node`](../api/src/mythrix/agent/graph/nodes/llm.py) |
| `tools` | deterministic | A `ToolNode` over `toolset.model_tools`, the fixed read-only tool set. | `langgraph.prebuilt.ToolNode` |
| `clarify` | deterministic | Builds a clarifying question straight from a tool result's `needs_*` payload — no model call. | [`graph/nodes/llm.py::clarify_node`](../api/src/mythrix/agent/graph/nodes/llm.py) |
| `fact_check` | model call | Classifies the reply's sentences against this turn's tool-returned evidence with a second, narrow model call — never given the reply's own text to reproduce, never loops back. | [`graph/nodes/fact_check.py::fact_check_node`](../api/src/mythrix/agent/graph/nodes/fact_check.py) |
| `parse_query` | deterministic | Parses an ad-hoc query into a pending confirmation. | [`graph/nodes/adhoc.py::parse_query_node`](../api/src/mythrix/agent/graph/nodes/adhoc.py) |
| `execute_query` | deterministic | Runs a previously parsed and confirmed ad-hoc query. | [`graph/nodes/adhoc.py::execute_query_node`](../api/src/mythrix/agent/graph/nodes/adhoc.py) |
| `summarize` | deterministic + 1 generative step | Fetches the active hotspot's passage, then summarizes it. | [`graph/nodes/summary.py::summarize_node`](../api/src/mythrix/agent/graph/nodes/summary.py) |
| `plan_augment` | deterministic | Plans a `/augment` run over the viewer's visible regions, returns a pending confirmation. | [`graph/nodes/augment.py::plan_augment_node`](../api/src/mythrix/agent/graph/nodes/augment.py) |
| `run_augment` | deterministic + many generative steps | Executes a confirmed `/augment` run: read → augment → hierarchical consolidation. | [`graph/nodes/augment.py::run_augment_node`](../api/src/mythrix/agent/graph/nodes/augment.py) |

Every deterministic node reaches `END` directly — none of the five command
nodes route through `agent` or `tools`; the orchestration model never sees a
command's own execution.

## 3. Command dispatch

`route_input` ([`graph/builder.py`](../api/src/mythrix/agent/graph/builder.py))
is the **only** place command dispatch happens, and it is a pure lookup — the
declared vocabulary itself lives in
[`agent/capabilities.py`](../api/src/mythrix/agent/capabilities.py)
(`AGENT_CAPABILITIES`), which `GET /api/agent/capabilities` serves to the
viewer so the frontend's command list can't drift from the backend's. This
table is that registry:

| Command | Args | Handled by | Listed | Summary |
|---|---|---|---|---|
| `/clear` | — | client | yes | Clear this thread and start a new session — no backend node exists for this one. |
| `/summarize` | — | server | yes | Summarize the passage selected in the viewer. |
| `/query` | `term[:exact\|:filter], …` | server | yes | Search the corpus on your own terms, with no sign selected. |
| `/query-confirm` | `<id>` | server | no | Run a parsed ad-hoc query. |
| `/augment` | `<what to look for>` | server | yes | Read every region on screen against a question and consolidate what recurs. |
| `/augment-confirm` | `<id>` | server | no | Run a parsed augmentation. |

Everything not matching one of the five server-handled commands above falls
through to `agent` — the ordinary conversational path.

`/query-confirm` and `/augment-confirm` are **not listed** (`listed: false`):
they exist for the viewer's own confirm affordance to invoke, not for a user
to type from memory. The pending confirmation each command produces is
round-tripped through the session via `PendingCommands`
(`agent/commands/__init__.py`) rather than held in graph state, since the
graph carries no state between turns.

## 4. The tool-calling loop

`agent` invokes the model with the fixed read-only tool set bound
(`toolset.model_tools`); a reply carrying tool calls routes to `tools`
(`route_after_agent`), which executes them and routes back to `agent`
(`route_after_tools`) — repeating until a reply carries no tool calls.

One interception sits in that loop: if a tool result is a JSON payload
carrying a truthy `needs_*` key (today, only `get_sign`'s `needs_tradition`),
`route_after_tools` sends it to `clarify` instead of back to `agent`.
`clarify_node` composes the clarifying question directly from the tool
payload's own candidate list — no model call — so the question can never
state anything the tool didn't actually return
([ADR-006](../specs/architecture-decisions/adr-006-conversational-agent-orchestration-boundary.md)).
`clarify` goes straight to `END`.

## 5. Post-hoc fact-checking

Every reply with no further tool calls is checked before it can end the
turn — `route_after_agent` sends it to `fact_check`, never straight to
`END`. Unlike every other node in this graph, `fact_check` makes a model
call of its own — a second, narrow call over this turn's evidence, distinct
from the primary tool-calling model
([ADR-025](../specs/architecture-decisions/adr-025-post-hoc-fact-checker-replaces-self-citation.md)).

The primary model's own prompt (`prompts.py::SYSTEM_PROMPT`) carries no
citation instruction at all — composing the answer is its only job.
`fact_check_node` finds this turn's own tool results via `turn_start_index`
(fixed once per turn) and builds an evidence list — source, locator, and
text for every citable item `get_sign`/`query_sign`/`fetch_segments`
returned — from `citation_grounding.py`. A turn with no such evidence (no
tool calls, or only enumeration tools), or a reply with no sentences at
all, is a no-op.

Otherwise, the reply is split into sentences deterministically, in code
(`fact_check.py::split_sentences`), and the fact-check model is given only
those numbered sentences and the evidence — never the reply's own text as
something to reproduce. It returns a compact JSON classification keyed by
sentence index (supported/not, and which evidence id(s) support it),
omitting a sentence entirely when it states no factual claim.
`fact_check_node` parses this into `SentenceVerdict`s and validates its
*structure* (a well-formed response, an in-range index, a boolean
`supported`) — there is nothing to reword, since the model was never given
custody of the reply's text to begin with:

- **Well-formed classification**: a `grounding_score`
  (`fact_check.py::grounding_score`) is computed from the parsed verdicts —
  a verdict counts as supported only when `supported=true` *and* at least
  one of its citations is a real evidence id, so the model's own boolean is
  never simply trusted. A `facts checked: NN%` footer is appended to the
  *original* reply's own text, unmodified. Individual per-sentence verdicts
  never reach the user; only the aggregate score does.
- **Model call failed, or the response could not be parsed into any usable
  verdicts**: the fact-checker's output is discarded and the original reply
  is used — with no footer. There is no retry, and grounding is never a
  reason to withhold the reply (`CITATION_FAILURE_MESSAGE` is not produced
  by this node at all).

This replaced the in-graph citation-retry loop
([ADR-023](../specs/architecture-decisions/adr-023-in-graph-citation-retry.md),
superseded), which asked the primary model to self-cite inline and gave it a
bounded number of corrective pushbacks when it got the marker syntax wrong.
An earlier draft of `fact_check_node` itself asked the fact-checker to echo
the reply back with tags inserted inline, verified by a no-reword text
comparison — replaced by the sentence-classification design above after
real-model testing found reproduction drift a small local model could not
reliably avoid, in several different shapes, regardless of how the tagging
instruction was worded (ADR-025's Revision section). `turn_service.py`'s own
marker check still runs, unchanged, as the sole gate for `/augment`'s `[R#]`
region markers and a redundant backstop on the conversational path — which
`fact_check_node` never trips in practice, since it no longer writes a
marker into the reply's text at all.

## 6. Bounds and the recursion budget

| Setting | Env var | Default | Governs |
|---|---|---|---|
| `agent_max_tool_iterations` | `MYTHRIX_AGENT_MAX_TOOL_ITERATIONS` | `16` | The graph's `recursion_limit` for one turn (`runner.py::stream_turn`) — every step through `agent` and `tools` counts against it, not just tool calls. `fact_check` runs at most once per turn and is not part of this loop. |
| `fact_check_model` | `MYTHRIX_FACT_CHECK_MODEL` | unset (falls back to `agent_model`, then `generation_model`) | Which model `fact_check_node` calls (ADR-025). |
| `augment_max_regions` | `MYTHRIX_AUGMENT_MAX_REGIONS` | `1000` | How many visible regions one `/augment` run reads. Does not consume `agent_max_tool_iterations` — `run_augment` is a deterministic node the model's tool loop never enters. |
| `augment_consolidation_group_size` | `MYTHRIX_AUGMENT_CONSOLIDATION_GROUP_SIZE` | `8` (min `2`) | How many results one hierarchical-consolidation call may be given, at every level of `/augment`'s reduce (§4.2 in architecture.md). |

Hitting the `agent_max_tool_iterations` limit ends the turn with a fixed
message (`runner.py`'s `_RECURSION_LIMIT_MESSAGE`) and discards the runaway
turn's messages — `TurnResult.history` is the history that was passed in.

## 7. Turn state

`AgentState` ([`graph/state.py`](../api/src/mythrix/agent/graph/state.py)):

| Field | Type | Notes |
|---|---|---|
| `messages` | `list` (`add_messages`) | The conversation, including this turn's tool messages and, once `fact_check` runs, the same reply text with a score footer appended. |
| `context_summary` | `str` | Folded into the system prompt by `agent_node`. |
| `pending_query` | `PendingAdhocQuery \| None` | Round-tripped through `PendingCommands`; the graph holds no state across turns. |
| `pending_augmentation` | `PendingAugmentation \| None` | Same, for `/augment`. |
| `instructions` | `list[dict]` | Instructions emitted for the viewer (e.g. `execute_query`, `augment_region`). |
| `region_id`, `interpretant`, `visible_regions` | turn-scoped inputs | The session's active hotspot and the consumer's current display; read by the deterministic nodes, never read back off final state. |
| `backend_authored` | `bool` | Marks a reply with no model-authored text, so `turn_service.py` can distinguish an ungrounded citation from a marker sequence the backend itself put there. |
| `turn_start_index` | `int` | Index into `messages` where this turn began; lets `fact_check_node` find this turn's tool messages and its own originating `HumanMessage`. |

## 8. Related specs and ADRs

- [`specs/interfaces/agent.md`](../specs/interfaces/agent.md) — the conversational agent's functional requirements.
- [`specs/interfaces/agent-capabilities.md`](../specs/interfaces/agent-capabilities.md) — the declared command/instruction vocabulary.
- [`specs/interfaces/agnostic-query.md`](../specs/interfaces/agnostic-query.md), [`specs/interfaces/augmentation.md`](../specs/interfaces/augmentation.md) — the two multi-step command flows.
- [ADR-006](../specs/architecture-decisions/adr-006-conversational-agent-orchestration-boundary.md) — orchestrate-not-retrieve boundary.
- [ADR-011](../specs/architecture-decisions/adr-011-backend-declared-agent-capabilities.md) — backend-declared capabilities.
- [ADR-012](../specs/architecture-decisions/adr-012-deterministic-command-nodes-bypass-tool-selection.md) — deterministic command nodes.
- [ADR-015](../specs/architecture-decisions/adr-015-deterministic-augmentation-over-viewer-regions.md), [ADR-016](../specs/architecture-decisions/adr-016-hierarchical-map-reduce-augmentation-consolidation.md) — `/augment`'s deterministic pipeline and consolidation shape.
- [ADR-022](../specs/architecture-decisions/adr-022-tool-owned-opaque-grounding-ids.md) — grounding id format.
- [ADR-023](../specs/architecture-decisions/adr-023-in-graph-citation-retry.md) — the in-graph citation retry loop, superseded by ADR-025.
- [ADR-025](../specs/architecture-decisions/adr-025-post-hoc-fact-checker-replaces-self-citation.md) — the post-hoc fact-check pass this document diagrams.
