# Plan — Region Augmentation (`/augment`)

Implements [spec.md](spec.md). Reworks the unmerged `/discover` feature: the
deterministic node and the two generative tools survive in shape, but their
input changes from a server-run ad-hoc query to a consumer-supplied region list,
and the turn's response changes from one JSON body to a stream of events.

## Control flow

```
POST /api/agent  →  application/x-ndjson
  routes.agent_turn                    StreamingResponse over the generator
    turn_service.stream_chat_turn      reads/writes session.pending_augmentation
      runner.stream_turn               seeds AgentState, forwards custom events
        graph route_input              head token → node; model never reached
          plan_augment_node            /augment
          run_augment_node             /augment-confirm
```

`run_augment_node`, in order:

1. head-truncate the pending region list to `augment_max_regions`
2. for each region `i` in 1..N, **in the supplied order**:
   `read_region(region_id)` → `{source, locator, text}` →
   `augment_passage(text, focus)` → augmentation → **emit two events**
3. `consolidate_augmentations(focus, augmentations)` → consolidation
4. compose the terminal reply

Generation invocations: **N+1**, all on the narrow `ChatClient`. The
orchestration model is not invoked, so `agent_max_tool_iterations` is never
consulted (FR-AU-21).

## Region input

`AgentTurnRequest` gains `visible_regions: list[str]`, a sibling of
`ui_selection` rather than a field inside it. `AgentContext` drives
`detect_thread_reset`; a list that changes on every keystroke in the search box
would reset the thread constantly, and FR-AG-17 already holds that the context
object carries no passage-scale data.

`turn_service` passes it to `runner.stream_turn`, which seeds it into
`AgentState["visible_regions"]` as a turn-scoped input — read by
`plan_augment_node`, never read back off the final state, exactly as
`region_id`/`interpretant` are today.

### Deriving a region (FR-AU-15)

`tools/read_region.py`, node-only, one call per region:

```
region_id "en_drb::1841-1844"
  parse_region_id                 → ("en_drb", 1841, 1844)   ValueError → skip
  graph_store.get_source          → citation_label or title  MythrixError → {"error"}
  fetch_source_segments(1841,1844)→ contiguous segments
  region_locator(segments)        → "Genesis 21:5–8"
  → {"region_id", "source", "source_id", "locator", "text"}
```

`text` is the segments joined — every ordinal in `[start, end]`, since
`ChromaVectorStore.get_segments` is a `$gte`/`$lte` range read with no match
test (FR-AU-17). Nothing is read outside the span (FR-AU-18).

`_region_locator` (`core/retrieval/pipeline.py:618`) becomes public
`region_locator`. It reproduces the query path's locator because a `region_id`'s
start/end *are* its first and last match-carrying ordinals, so the first and
last locators over the full range are the same two the pipeline merged.

This collapses the node's current two-step (`parse_region_id` inline, then
`fetch_segments`) into one tool, and is why `query_adhoc` leaves the tool set
with no replacement: the node no longer retrieves.

## Streaming

The turn is already internally a stream — `runner.run_turn` consumes
`graph.stream(...)` and collapses it. The collapse moves outward.

**Event models** (`turn_service.py`), discriminated on `event`:

| model | fields |
|---|---|
| `MessageEvent` | `event="message"`, `text` |
| `InstructionEvent` | `event="instruction"`, `instruction: AgentInstruction` |
| `TurnEvent` | `event="turn"`, `context`, `reply_text`, `instructions`, `thread_reset` |

`TurnEvent` carries exactly today's `AgentTurnResponse` fields; the class is
renamed rather than duplicated.

**Node → stream.** `run_augment_node` calls `get_stream_writer()` (langgraph
1.2.9) once and writes a dict per region completion. `runner.stream_turn` runs
`graph.stream(..., stream_mode=["values", "custom"])`, which yields
`(mode, payload)` tuples: `"values"` payloads drive the existing state/logging
loop, `"custom"` payloads are yielded straight through. The generator's last
yield is the `TurnResult`.

**Service.** `run_chat_turn` becomes `stream_chat_turn`, a generator. Its
existing body is unchanged up to the `run_turn` call; every `return
AgentTurnResponse(...)` becomes `yield TurnEvent(...); return`. The
`with sessions.lock_for(session_id)` block wraps the yields, so an abandoned
response releases the lock through `GeneratorExit`.

`run_chat_turn` survives as a module-private drain returning the terminal event,
used by the existing turn-service tests and available to a future CLI. It is not
routed to.

**Route.** `agent_turn` returns
`StreamingResponse(_ndjson(...), media_type="application/x-ndjson")`, where
`_ndjson` serializes each event with `model_dump_json()` and appends `\n`.
`response_model` is dropped. FastAPI resolves `Depends(get_agent_graph)` before
the first yield, so an unconfigured model still fails as a 502 (FR-AU-25 governs
only failures after the first event, which `stream_chat_turn` already converts
to a `TurnEvent` carrying `_TOOL_FAILURE_MESSAGE`).

## Node and command modules

`commands/augment.py` — pure, no LangGraph import:

- `AUGMENT_COMMAND = "/augment"`, `AUGMENT_CONFIRM_COMMAND = "/augment-confirm"`
- `PendingAugmentation(id, focus, region_ids)`
- `parse_augment_command(message) -> str` — the trimmed remainder;
  `AdhocQueryValidationError` when empty (FR-AU-03)
- `region_label(rank)`, `new_augmentation_id`, `confirm_id_of`,
  `confirm_command_for`
- `render_plan(focus, supplied, augmenting, id)`,
  `render_reply(consolidation, supplied, augmented)`,
  `confirm_augment_instruction(...)`, `augment_region_instruction(...)`
- `NO_REGIONS_MESSAGE`, `NO_PASSAGE_MESSAGE`

`graph/nodes/augment.py` — `plan_augment_node(state, *, max_regions)` and
`run_augment_node(state, tools, *, max_regions)`. `_backend_reply` carries over
unchanged (FR-AU-27's system-authored exemption).

The one fabricated tool-call/`ToolMessage` pair a run records is named
`augment_regions` and carries the region records of FR-AU-32 — replacing the
`query_adhoc` pair, and keeping `_build_valid_marker_ids`' `[R#]` accounting
working by the same mechanism.

## Prompts and tools

`analyze_passage` → `augment_passage(passage_text, focus)`;
`consolidate_findings` → `consolidate_augmentations(focus, augmentations)`. Both
lose `concepts`, which the working tree's prompt edits had already stopped
using. `render_augmentation_prompt` / `render_consolidation_prompt` lose it too.

`ToolSet.node_tools` becomes `[read_region, augment_passage,
consolidate_augmentations]`. `tools/query_adhoc.py` is deleted, and with it the
`include_segments` parameter `_render_regions` grew for it alone.
`POST /api/query/adhoc` and `core.query_service.execute_adhoc_query` are
untouched — they serve `/query`'s `execute_query` instruction, which is a
separate path.

## Capabilities

`InstructionType` gains `confirm_augment` and `augment_region`, both
`binding=None`; `confirm_discovery` goes. Two `CommandSpec`s replace the
discovery pair.

`augment_region` with no binding is what lets iteration 1 ship safely:
`executeInstruction` returns `null` for it, so `runInstructions` skips it
without the "this build doesn't know how to run…" error an undeclared type
would produce (FR-CAP-13). Iteration 2 gives it a renderer with no backend
change.

## Web

Transport and state:

- `api/types.ts` — `visible_regions` on the request wire; the three event wire
  shapes; an `Augmentation { text, label }` view type.
- `api/client.ts` — `postAgentTurn` → `streamAgentTurn(sessionId, message,
  uiSelection, visibleRegionIds, onEvent)`. Reads `response.body` through a
  `TextDecoder`, buffers partial lines, `JSON.parse`s each complete one,
  dispatches to `onEvent`, returns the terminal event.
- `state/useTabs.ts` — `Tab` gains `augmentations: Record<string, Augmentation>`.
  Sends `rankedHotspots.map((h) => h.regionId)`; appends an `ai` `ThreadItem` per
  `message` event as it arrives; merges each `augment_region` instruction into
  `augmentations` keyed by `region_id` (FR-AU-26); clears the map wherever
  `queryResult` is replaced — `runQuery` and the `execute_query` branch of
  `runInstructions` (FR-AU-29).
- `api/instructions.ts` — unchanged. `augment_region` is declared with
  `binding=null`, so `executeInstruction` returns `null` and the by-type handling
  happens in `useTabs`, exactly as `confirm_query` is handled by type in the
  panel. No new `ResultKind`, so FR-CAP-11 is untouched.

Rendering, per `mythrix-augmentation.html`:

- `components/SparkleIcon.tsx` — the mark, extracted like `ConvergenceIcon`
  already is, since both the card and the reader use it.
- `components/HotspotCard.tsx` — new `isAugmented` prop; renders
  `<span className="augmented-mark" title="Has AI analysis">` inside `.hc-title`
  after the title text (FR-AU-27).
- `components/HotspotDetailPanel.tsx` — new `augmentation` prop; renders the
  `.augmented-section` block between the chip row (and its dimmed note) and
  `.reader-actions`, so it precedes the verbatim `.segment-list` and cannot read
  as part of the source text (FR-AU-28).
- `components/HotspotList.tsx`, `App.tsx` — thread `augmentations` down.
- `index.css` — `.augmented-mark`, `.augmented-section`, `.augmented-head`,
  ported from the mockup onto the existing `--violet` / `--violet-wash` tokens.

`generatedAt` appears in the mockup's fixture data but is never rendered; it is
not carried.

## Trade-offs

- **One streaming endpoint, not two.** A second non-streaming endpoint would
  have to keep its body equal to the terminal event, an invariant nothing
  enforces. The cost is that `AgentTurnResponse` stops being a `response_model`,
  so OpenAPI no longer types the body, and every consumer parses NDJSON even for
  a one-line reply.
- **The run executes inside the turn, not behind an instruction.** `/augment-confirm`
  could have mirrored `/query-confirm`: emit an `execute_augment` instruction
  bound to a new streaming endpoint and let the consumer dial it, leaving
  `POST /api/agent` as plain JSON. Rejected because the turn would then end when
  the instruction is emitted — the consolidation would arrive on a second
  connection and have to be injected into the thread out-of-band, placing it
  outside conversation history (FR-AU-30), outside citation validation, and
  outside `[R#]` marker accounting. It would also require reworking the closed
  binding vocabulary, which is typed around one request yielding one result
  (`RESULT_HANDLERS: Record<ResultKind, …> → ExecutionOutcome`).
- **Snapshot at plan time** (FR-AU-09). The plan states an exact count, so
  running against a list the user has since re-filtered would contradict it. The
  cost is that a user who narrows the facets after seeing the plan must re-issue
  `/augment`.
- **Client-supplied region list.** The alternative — re-running the query and
  re-applying the facets and search box server-side — would duplicate
  `rankedHotspots`' filter and sort in Python, free to drift, and cost a second
  retrieval. FR-AU-15 contains the resulting trust surface: only the identity is
  taken, everything else is derived.
- **The record of augmented regions is fabricated, not a real tool call.** It
  keeps citation accounting and history shape unchanged while a run's per-region
  work stays out of the thread the next turn replays (FR-AU-31).

## ADR

`adr-015-deterministic-analysis-over-adhoc-retrieval.md` is renamed to
`adr-015-deterministic-augmentation-over-viewer-regions.md` and rewritten: its
decision — that a deterministic command may run ad-hoc retrieval server-side —
is the one this change reverses, and it has never reached `main`. The restated
decision covers the consumer-supplied region list, the model-selectable vs
node-only tool split (retained), bounded generation fan-out with a reduced
history record (retained), and streaming a turn as events.
