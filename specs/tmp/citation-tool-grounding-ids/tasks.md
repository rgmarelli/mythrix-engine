# Tasks: tool-owned grounding ids

- [x] Write ADR-022 and add it to `specs/architecture-decisions/README.md`'s index.
- [x] Write `spec.md`/`plan.md`/`tasks.md` (this file).
- [x] Add `_new_grounding_id` helper to `agent/tools/_shared.py`; wire into `_render_graph_facts` (G) and `_render_regions` (S).
- [x] Revert `agent/tools/fetch_segments.py` to a plain `@tool`; add `grounding_id` per segment.
- [x] Remove `citation_count` from `agent/graph/state.py` (`AgentState`) and `agent/runner.py` (initial state dict).
- [x] Simplify `agent/turn_service.py::_build_valid_marker_ids` to read `grounding_id` for `get_sign`/`query_sign`/`fetch_segments`; remove the debug `print` and dead commented-out line in `_ungrounded_markers`. Also restored the accidentally dead-coded marker-stripping line (`reply_text = strip_markers(visible_reply)` was being immediately overwritten) and removed a stray `# FIXME` left from the same uncommitted session.
- [x] Widen `agent/citations.py`'s marker regex for `G`/`S`/`C` to accept hex-alnum ids; leave `R` digit-only.
- [x] Restore `agent/prompts.py::SYSTEM_PROMPT` to committed `HEAD` content, then replace only the citation-indexing lines; delete `SYSTEM_PROMPT_TEST`.
- [x] Update `test_get_sign.py`, `test_fetch_segments.py`, `test_agent_turn_service.py` for the new `grounding_id` shape. Also updated `test_api.py`'s `_fake_get_sign` fixture (integration-level `/api/agent` test), found via a full-suite run after the targeted suite passed.
- [x] `ruff check .` / `ruff format .` over changed files — clean.
- [x] Run the targeted pytest suite (`test_get_sign.py`, `test_query_sign.py`, `test_fetch_segments.py`, `test_agent_turn_service.py`, `test_agent_citations.py`) — 74 passed.
- [x] Run the full `tests/unit` suite as a final check — 538 passed.
