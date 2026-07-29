# Tasks — Region Augmentation (`/augment`)

Derived from [plan.md](plan.md). Ordered so each step is independently
verifiable and the suite stays green throughout.

## Decide

- [x] 1. Rewrite `specs/architecture-decisions/adr-015-deterministic-analysis-over-adhoc-retrieval.md`
      as `adr-015-deterministic-augmentation-over-viewer-regions.md` (Context /
      Decision / Consequences / Alternatives considered): consumer-supplied
      region list, model-selectable vs node-only tool split, bounded generation
      fan-out with a reduced history record, and a turn streamed as events.
      Update the row in `architecture-decisions/README.md`. Agree before any code.

## Foundations

- [x] 2. `core/config.py`: rename `discover_max_regions` → `augment_max_regions`
      (default 8) and rewrite its docstring paragraph. Update
      `tests/unit/test_config.py`.
- [x] 3. `core/retrieval/pipeline.py`: promote `_region_locator` to public
      `region_locator`; update its one internal caller. Extend
      `tests/unit/test_retrieval_pipeline.py` with a direct test of the
      single-segment and merged-locator cases.
- [x] 4. `agent/tools/_shared.py`: drop `_render_regions`' `include_segments`
      parameter and the branch it guards.

## Region reading

- [x] 5. `agent/tools/read_region.py`: `read_region(region_id)` →
      `{region_id, source, source_id, locator, text}`, or `{"error": ...}`. A
      malformed id raises no exception — it returns an error result.
- [x] 6. `tests/unit/agent_tools/test_read_region.py`: full contiguous range
      including non-matching interior ordinals; locator matches the query path's;
      source falls back from `citation_label` to `title`; malformed id, unknown
      source, and empty range each return an error result.
- [x] 7. `agent/tools/__init__.py`: `node_tools` becomes `[read_region,
      augment_passage, consolidate_augmentations]`; delete
      `agent/tools/query_adhoc.py` and `tests/unit/agent_tools/test_query_adhoc.py`.

## Generation tools and prompts

- [x] 8. `agent/prompts.py`: `render_passage_analysis_prompt` →
      `render_augmentation_prompt(text, focus)`;
      `render_discovery_consolidation_prompt` → `render_consolidation_prompt(focus,
      augmentations)`. Both lose `concepts`. Remove the `# FIXME: remove` block
      at EOF and the trailing-newline defect. Update
      `tests/unit/test_agent_prompts.py` to the new contract.
- [x] 9. `agent/tools/analyze_passage.py` → `augment_passage.py`
      (`augment_passage(passage_text, focus)`);
      `agent/tools/consolidate_findings.py` → `consolidate_augmentations.py`
      (`consolidate_augmentations(focus, augmentations)`). Rename their test
      modules and drop every `concepts` assertion.

## Command parsing

- [x] 10. `agent/commands/augment.py`: `AUGMENT_COMMAND`,
      `AUGMENT_CONFIRM_COMMAND`, `PendingAugmentation(id, focus, region_ids)`,
      `command_of`, `parse_augment_command`, `confirm_id_of`,
      `new_augmentation_id`, `confirm_command_for`, `region_label`.
- [x] 11. `agent/commands/augment.py`: `render_plan`, `render_reply`,
      `confirm_augment_instruction`, `augment_region_instruction`,
      `NO_REGIONS_MESSAGE`, `NO_PASSAGE_MESSAGE`.
- [x] 12. `tests/unit/test_agent_commands_augment.py`: head-token matching
      (`/augment-confirm` is not `/augment`); focus is taken verbatim including
      commas, colons and quotes; empty focus rejected; label numbering leaves a
      gap for a skipped rank; plan states both counts. Delete
      `tests/unit/test_agent_commands_discover.py`.

## Streaming transport

- [x] 13. `agent/turn_service.py`: add `MessageEvent`/`InstructionEvent`;
      rename `AgentTurnResponse` → `TurnEvent` with an `event` discriminator.
- [x] 14. `agent/runner.py`: `run_turn` → `stream_turn` generator;
      `stream_mode=["values", "custom"]`; `"custom"` payloads yielded through,
      `"values"` payloads driving the existing state and logging loop; final
      yield is the `TurnResult`. Rename `pending_discovery` →
      `pending_augmentation` throughout.
- [x] 15. `agent/turn_service.py`: `run_chat_turn` → `stream_chat_turn`
      generator; every response path becomes `yield TurnEvent(...); return`,
      with the session lock wrapping the yields. Keep a private `run_chat_turn`
      drain returning the terminal event.
- [x] 16. `api/routes.py`: `AgentTurnRequest` gains `visible_regions:
      list[str] = []`; `agent_turn` returns a `StreamingResponse` of NDJSON;
      drop `response_model`.
- [x] 17. `tests/unit/test_agent_turn_service.py`: event order for an ordinary
      turn (terminal event alone); the lock released when the generator is
      closed early; a mid-turn `MythrixError` delivered as a `TurnEvent`, not an
      exception. `tests/integration/` (or the route test): a real NDJSON body
      parses line-by-line and the last line is the terminal event.

## Node

- [x] 18. `agent/graph/state.py`: `pending_discovery` → `pending_augmentation`;
      add turn-scoped `visible_regions: list[str]`.
- [x] 19. `agent/graph/nodes/augment.py`: `plan_augment_node` — parse, reject an
      empty focus or an empty region list, snapshot into `PendingAugmentation`,
      reply with the plan, emit `confirm_augment`.
- [x] 20. `agent/graph/nodes/augment.py`: `run_augment_node` — head-truncate,
      then per region `read_region` → `augment_passage` → `get_stream_writer()`
      message + instruction; then `consolidate_augmentations`; then the
      `augment_regions` record pair and the terminal reply. Delete
      `agent/graph/nodes/discover.py`.
- [x] 21. `agent/graph/builder.py` + `agent/commands/__init__.py` +
      `api/dependencies.py`: route `plan_augment`/`run_augment`; register
      `augment.command_of`; pass `augment_max_regions`.
- [x] 22. `agent/turn_service.py`: `_build_valid_marker_ids`' `query_adhoc`
      branch → `augment_regions`.
- [x] 23. `agent/capabilities.py`: two `CommandSpec`s and two
      `InstructionSpec`s (`confirm_augment`, `augment_region`, both
      `binding=None`); drop the discovery entries. Update
      `tests/unit/test_agent_capabilities.py`.
- [x] 24. `tests/unit/test_agent_graph_nodes_augment.py` (+ `graph_helpers.py`,
      `test_agent_graph_builder.py`): N+1 generation calls for N regions; the
      supplied order preserved; a malformed id skipped leaving a label gap;
      truncation past the bound; snapshot honoured when the confirm turn carries
      a different region list; one event pair per region, all before the
      terminal event; the orchestration model never invoked. Delete
      `test_agent_graph_nodes_discover.py`.

## Web

- [x] 25. `web/src/api/types.ts`: `visible_regions`; `AgentTurnEventWire` union.
- [x] 26. `web/src/api/client.ts`: `streamAgentTurn` with a buffered
      line-splitting reader. `client.test.ts`: a chunked body split mid-line
      parses correctly; a trailing line with no newline is delivered.
- [x] 27. `web/src/state/useTabs.ts`: `Tab.augmentations`; send the visible
      region ids; append a thread item per `message` event; merge each
      `augment_region` instruction by `region_id`; clear the map in `runQuery`
      and on an `execute_query` result. `useTabs.test.ts`: ids sent match
      `rankedHotspots`; per-region items appear before the final reply; an
      `augment_region` instruction lands in `augmentations` and produces no
      error item; a re-query clears them.
- [x] 28. `web/src/components/AgentChatPanel.tsx`: `CONFIRM_LABELS` gains
      `confirm_augment`. Update `AgentChatPanel.test.tsx`.
- [x] 28a. `web/src/components/SparkleIcon.tsx`; `HotspotCard.tsx` gains
      `isAugmented` and renders the mark inside `.hc-title` (FR-AU-27);
      `HotspotList.tsx`/`App.tsx` thread `augmentations` down. Extend
      `HotspotCard.test.tsx`/`HotspotList.test.tsx`.
- [x] 28b. `web/src/components/HotspotDetailPanel.tsx` gains `augmentation` and
      renders `.augmented-section` between the chip row and `.reader-actions`
      (FR-AU-28). Extend `HotspotDetailPanel.test.tsx`: the block appears only
      when an augmentation exists, and precedes the segment list.
- [x] 28c. `web/src/index.css`: `.augmented-mark`, `.augmented-section`,
      `.augmented-head`, ported from `mythrix-augmentation.html` onto the
      existing violet tokens.

## Specs

- [x] 29. `specs/interfaces/discovery.md` → `specs/interfaces/augmentation.md`,
      renumbered `FR-DS` → `FR-AU` from [spec.md](spec.md).
- [x] 30. `specs/interfaces/api.md`, `agent.md`, `agent-capabilities.md`,
      `web-viewer.md`: the turn's response is a stream of events; the turn
      carries the consumer's visible regions. `specs/spec.md`: §3 goal, §5.2
      concept, §6 pointer, §10 index row.

## Verify

- [x] 31. `uv run ruff check . && uv run ruff format .`; `uv run pytest`;
      `npx vitest run && npx tsc -b --noEmit && npx oxlint` in `web/`;
      `test_domain_agnosticism.py` green.
- [ ] 32. Manual against live Ollama: query a sign, narrow with a facet and the
      search box, `/augment <focus>`, confirm the plan's count equals the
      visible count, click the chip, watch per-region lines arrive ahead of the
      consolidation. Cross-check the INFO log and a raw `curl -N` body.
