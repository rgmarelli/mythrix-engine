# Tasks: in-graph citation retry

- [x] Write ADR-023 and add it to `specs/architecture-decisions/README.md`'s index.
- [x] Write `spec.md`/`plan.md`/`tasks.md` (this file).
- [x] Add `turn_start_index` to `AgentState` (`agent/graph/state.py`); set it in `runner.py::stream_turn`'s initial state dict.
- [x] Add `agent/citation_grounding.py` (`only_listing_tools_called`, `grounding_ids`).
- [x] Move `CITATION_FAILURE_MESSAGE` to `agent/citations.py`, public.
- [x] Refactor `turn_service.py::_build_valid_marker_ids`/`_only_listing_tools_called` to delegate to `citation_grounding`; import `CITATION_FAILURE_MESSAGE` from `citations.py`. Also added a dedicated check in `stream_chat_turn` for the graph's own exhausted-retries fallback text, so history still isn't persisted and the failure is still logged for that path (found via the full unit suite, not originally itemized).
- [x] Add `render_citation_pushback` to `agent/prompts.py`.
- [x] Add `agent/graph/nodes/citation_check.py` (`validate_citations_node`, `route_after_citation_check`).
- [x] Wire the new node into `agent/graph/builder.py`; `compile_agent_graph` gains `citation_max_retries`. `route_after_agent` updated to route to `validate_citations` instead of `END`.
- [x] Add `Settings.citation_max_retries` (default 2); wire through `api/dependencies.py::get_agent_graph`.
- [x] Update `tests/unit/graph_helpers.py::compile_graph` with `citation_max_retries: int = 0` default.
- [x] Add `tests/unit/test_agent_citation_grounding.py` (9 tests).
- [x] Add retry/pushback/self-correction/exhausted-fallback tests to `tests/unit/test_agent_turn_service.py`; updated 2 pre-existing tests (`test_route_after_agent_routes_to_end_when_no_tool_calls` renamed/retargeted; `validate_citations_node` made defensive with `state.get("turn_start_index", 0)` so tests driving the graph directly, without `runner.py`, don't KeyError).
- [x] `ruff check .` / `ruff format .` over changed files — clean.
- [x] Run the full `tests/unit` suite — 550 passed.
- [x] Wire `citation_max_retries=2` into `tests/integration/test_agent_grounding_ids.py`'s `graph` fixture; rerun against real `qwen3:1.7b`: **5 passed, 1 failed** (up from the pre-ADR-023 baseline of 1/6). The one remaining failure (`query_sign_reply_cites_real_opaque_segment_ids_when_asked_to_cite`) is a model habit the retry loop couldn't correct even after two pushbacks: it consistently substituted its own `[Genesis::0-4]`-style region reference for the tool's real `grounding_id` (e.g. `S917f0b`) — reported honestly, not tuned further.
