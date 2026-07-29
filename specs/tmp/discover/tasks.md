# Tasks — Corpus Discovery (`/discover`)

Derived from [plan.md](plan.md). Ordered so each step is independently
verifiable and the suite stays green throughout.

## Decide

- [x] 1. `specs/architecture-decisions/adr-015-deterministic-analysis-over-adhoc-retrieval.md`:
      write it (Context / Decision / Consequences / Alternatives considered),
      covering server-side ad-hoc retrieval inside a deterministic turn, the
      model-selectable vs node-only tool split, and bounded generation fan-out
      with a reduced history record. Add the row to
      `architecture-decisions/README.md`. Agree before any code.

## Foundations

- [x] 2. `core/config.py`: add `discover_max_regions: int = 8`. Extend
      `tests/unit/test_config.py`.
- [x] 3. `agent/citations.py`: split `_MARKER_PATTERN` (validated, gains
      `R\d+`) from `_STRIP_PATTERN` (removed from replies, unchanged
      `G|S|C`); point `strip_markers` at the latter. Update the module
      docstring. Extend `tests/unit/test_citation_resolution.py`: `R` is
      validated, `R` survives stripping, `G`/`S`/`C` behavior unchanged.
- [x] 4. `agent/commands/adhoc.py`: extract `parse_terms(text) -> tuple[AdhocTerm, ...]`
      from `parse_query_command`; the latter becomes a caller. No behavior
      change — `tests/unit/test_agent_commands_adhoc.py` passes untouched.
- [x] 5. `agent/tools/_shared.py`: add `_generated(chat_client, prompt, key)`;
      add `include_segments: bool = True` to `_render_regions`. Rewrite
      `tools/summarize_passage.py` onto `_generated` with no behavior change —
      `tests/unit/agent_tools/test_summarize_passage.py` passes untouched.

## Command parsing

- [x] 6. `agent/commands/discover.py`: `DISCOVER_COMMAND`,
      `DISCOVER_CONFIRM_COMMAND`, `PendingDiscovery`, `command_of`,
      `parse_discover_command` (quoted focus + `parse_terms` on the remainder),
      `confirm_id_of`, `new_discovery_id`, `confirm_command_for`.
- [x] 7. `agent/commands/discover.py`: `render_plan(focus, terms, max_regions, id)`
      and `render_report(focus, terms, matched, findings, consolidation)`.
- [x] 8. `tests/unit/test_agent_commands_discover.py`: head-token matching
      (`/discovered` must not match), focus containing commas/colons/directive
      suffixes, and each FR-DS-02 rejection (no quotes, unterminated quote,
      empty focus, no terms). Rendering assertions for both renderers.
- [x] 9. `agent/commands/__init__.py`: register `discover.command_of` in
      `_HANDLERS`; export `discover`.

## Tools

- [x] 10. `agent/tools/query_adhoc.py`: `query_adhoc(terms, limit)` wrapping
      `query_service.execute_adhoc_query`, returning
      `{"matched_count": int, "regions": [...]}` head-truncated to `limit`,
      rendered with `include_segments=False`.
- [x] 11. `agent/prompts.py`: `render_passage_analysis_prompt(text, focus, concepts)`
      and `render_discovery_consolidation_prompt(focus, findings, concepts)`.
      `SYSTEM_PROMPT` and `render_passage_summary_prompt` untouched. Extend
      `tests/unit/test_agent_prompts.py`.
- [x] 12. `agent/tools/analyze_passage.py` and
      `agent/tools/consolidate_findings.py`, each one `_generated` call.
- [x] 13. `agent/tools/__init__.py`: add `ToolSet(model_tools, node_tools, all)`;
      `build_tools` returns it, with the three new tools in `node_tools`.
- [x] 14. `tests/unit/agent_tools/test_query_adhoc.py`,
      `test_analyze_passage.py`, `test_consolidate_findings.py` — happy path,
      truncation, and `MythrixError` → `{"error": …}`. Extend
      `tests/unit/agent_tools/test_build.py` for the `ToolSet` split.

## Graph

- [x] 15. `agent/graph/state.py`: add `pending_discovery`, `backend_authored`.
- [x] 16. `agent/graph/nodes/discover.py`: `plan_discovery_node` — parse, mint
      id, set `pending_discovery`, `backend_authored=True`; parse failure drops
      any outstanding discovery (FR-DS-08).
- [x] 17. `agent/graph/nodes/discover.py`: `run_discovery_node` — id gate,
      `query_adhoc`, the per-region `fetch_segments` → `analyze_passage` loop in
      retrieval order, `consolidate_findings`, `strip_markers` on every
      generated string, report composition, and the fabricated `query_adhoc`
      message pair as the only history addition.
- [x] 18. `agent/graph/nodes/discover.py`: the INFO log lines listed in plan.md
      (plan, run start, per-region start/done with elapsed, consolidate, done).
- [x] 19. `agent/graph/builder.py`: `route_input` branches; register both nodes;
      edges to `END`; `ToolNode(toolset.model_tools)`; `summarize_node` gets
      `toolset.all`; signature becomes
      `compile_agent_graph(llm_with_tools, toolset, *, discover_max_regions)`.
      Update existing call sites in `tests/unit/test_agent_graph_builder.py`.
- [x] 20. `tests/unit/test_agent_graph_nodes_discover.py`: tool call order;
      exactly N+1 generation calls; region order equals retrieval's;
      truncation to the bound; no-regions path invokes no model; unmatched
      confirm id runs nothing and preserves the pending discovery; findings are
      marker-stripped; history holds only the `query_adhoc` pair plus the report.
- [x] 21. `tests/unit/test_agent_graph_builder.py`: both commands reach neither
      `agent` nor `ToolNode`; `node_tools` are absent from `ToolNode`.

## Turn plumbing

- [x] 22. `agent/sessions.py`: `SessionState.pending_discovery`.
- [x] 23. `agent/runner.py`: `run_turn(..., pending_discovery=None)`; seed both
      new state keys; `TurnResult` gains `pending_discovery` and
      `backend_authored`, read off the final state (and preserved on the
      `GraphRecursionError` path).
- [x] 24. `agent/turn_service.py`: clear `pending_discovery` on thread reset;
      persist it from `TurnResult`; skip citation validation when
      `result.backend_authored`; add the `query_adhoc` → `R{n}` branch to
      `_build_valid_marker_ids`.
- [x] 25. `tests/unit/test_agent_turn_service.py` and
      `tests/unit/test_agent_runner.py`: `R` id accounting, `backend_authored`
      bypass, `pending_discovery` lifecycle across turns and thread reset.

## Registration

- [x] 26. `agent/capabilities.py`: two `CommandSpec`s with names imported from
      `commands/discover.py` — `/discover` listed, `/discover-confirm` not.
      Extend `tests/unit/test_agent_capabilities.py`.
- [x] 27. `api/dependencies.py`: bind `toolset.model_tools`; pass `toolset` and
      `settings.discover_max_regions` to `compile_agent_graph`. Check
      `tests/unit/test_api_dependencies.py`.

## Close out

- [x] 28. `ruff check . && ruff format .`; full `pytest` including
      `test_domain_agnosticism.py` (CON-SYS-01).
- [ ] 29. Manual run against a live Ollama: `/discover "…", joy, laughter` then
      `/discover-confirm <id>`; read the INFO log for step sequence, per-region
      timings and N+1 generation calls; confirm `[R#]` markers survive into the
      rendered reply and line up with the report's sections.
- [x] 30. Fold `spec.md` into `specs/interfaces/discovery.md`; update
      `specs/spec.md` §3 Goals, §5.2 Core Concepts, a new §6.N pointer, the §10
      Requirements Index row (`FR-DS` / FR-DS-01–FR-DS-30) and the active
      requirement count; add the §8 flow if warranted. Delete `specs/tmp/discover/`
      only on explicit confirmation.

## Confirmation chip (FR-DS-31, added after §Implement)

- [x] 31. `agent/commands/discover.py`: `confirm_discovery_instruction(id, focus, terms)`.
- [x] 32. `agent/graph/nodes/discover.py`: `plan_discovery_node` emits it; a
      parse failure emits none.
- [x] 33. `agent/capabilities.py`: `InstructionType` gains `"confirm_discovery"`;
      one `InstructionSpec` with `binding=None`. `agent/turn_service.py`:
      `AgentInstruction.type` Literal gains it. Extend
      `tests/unit/test_agent_capabilities.py`.
- [x] 34. `web/src/components/AgentChatPanel.tsx`: `ConfirmActions` renders a
      chip per confirmable instruction, labeled by type.
- [x] 35. Tests: `test_agent_graph_nodes_discover.py`,
      `test_agent_turn_service.py`, `AgentChatPanel.test.tsx`,
      `useTabs.test.ts` (declared-but-unbound type runs nothing).
- [x] 36. `ruff check/format`, `pytest`, and the web suite.
