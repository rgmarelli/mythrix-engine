# Plan: in-graph citation retry

Mirrors the approved plan at `/Users/rgmarelli/.claude/plans/we-need-to-make-declarative-waterfall.md`; see ADR-023 for full rationale.

1. **`agent/graph/state.py`**: add `turn_start_index: int` to `AgentState` — the index in `state["messages"]` where this turn's own messages begin, fixed once per turn so the retry loop can find "this turn's tool messages" regardless of how many pushback `HumanMessage`s have since been appended.

2. **`agent/runner.py`**: `stream_turn` passes `"turn_start_index": len(history)` in the initial state dict, alongside the other turn-scoped inputs (`region_id`, `interpretant`, `visible_regions`).

3. **`agent/citation_grounding.py`** (new): `only_listing_tools_called(tool_messages)` and `grounding_ids(tool_messages)` — the `get_sign`/`query_sign`/`fetch_segments` extraction currently inline in `turn_service.py::_build_valid_marker_ids`, moved here so both `turn_service.py` and the new graph node can use it without a backwards dependency (`citations.py` stays typeless by design; `turn_service.py` is a higher-level orchestrator the graph shouldn't depend on).

4. **`agent/citations.py`**: `CITATION_FAILURE_MESSAGE` becomes a public constant here (moved from `turn_service.py`'s private `_CITATION_FAILURE_MESSAGE`), so the new node's exhausted-retries fallback and `turn_service.py`'s own backstop show identical text.

5. **`agent/turn_service.py`**: `_build_valid_marker_ids` calls `citation_grounding.grounding_ids(tool_messages)` for the G/S/fetch_segments ids, then still adds its own `augment_regions`/R-label loop on top. `_only_listing_tools_called` delegates to `citation_grounding.only_listing_tools_called`. Behavior for `/augment` and as the conversational-path backstop is unchanged.

6. **`agent/prompts.py`**: `render_citation_pushback(invalid_markers: tuple[str, ...]) -> str` — approved wording, names the invalid marker(s), instructs the model to reanswer using only the valid bracketed ids shown.

7. **`agent/graph/nodes/citation_check.py`** (new): `validate_citations_node(state, *, max_retries)` and `route_after_citation_check(state)`, per ADR-023's Decision section.

8. **`agent/graph/builder.py`**: `route_after_agent`'s no-tool-calls branch returns `"validate_citations"` instead of `END`; register the new node (closing over `citation_max_retries`, same pattern as `plan_augment`/`run_augment`); add the new conditional edge. `compile_agent_graph` gains a `citation_max_retries: int` keyword.

9. **`core/config.py`**: `Settings.citation_max_retries: int = 2`, documented alongside `agent_max_tool_iterations`.

10. **`api/dependencies.py`**: `get_agent_graph` passes `citation_max_retries=settings.citation_max_retries` to `compile_agent_graph`.

11. **`tests/unit/graph_helpers.py`**: `compile_graph` gains `citation_max_retries: int = 0` — deliberately 0, not the production default, so every existing scripted test that doesn't care about retries keeps working unchanged (0 retries = today's immediate-fallback behavior).

12. **`tests/unit/test_agent_citation_grounding.py`** (new): unit tests for the two extracted functions.

13. **`tests/unit/test_agent_turn_service.py`**: new tests for the pushback message, self-correction on retry, exhausted-retries fallback, and listing-only-turn skip — using `citation_max_retries=1` or `2` explicitly where retries are exercised.

14. **`tests/integration/test_agent_grounding_ids.py`**: wire `citation_max_retries=2` into the `graph` fixture; rerun against real `qwen3:1.7b` and report the outcome honestly.
