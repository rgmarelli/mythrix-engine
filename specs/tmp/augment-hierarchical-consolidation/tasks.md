# Tasks: Hierarchical consolidation for `/augment`

## Config

- [ ] Add `augment_consolidation_group_size: int = Field(default=8, ge=2)` to `Settings` in `api/src/mythrix/core/config.py`, with a docstring paragraph beside `augment_max_regions`'s (import `Field` from `pydantic`).

## Prompt

- [ ] Add `render_rollup_prompt(focus: str, summaries: tuple[str, ...]) -> str` to `api/src/mythrix/agent/prompts.py`, instructing verbatim marker preservation across already-synthesized summaries.

## New tool

- [ ] Add `api/src/mythrix/agent/tools/rollup_augmentations.py` with `build_rollup_augmentations_tool(chat_client)`.
- [ ] Register the new tool in `node_tools` in `api/src/mythrix/agent/tools/__init__.py`; update the module docstring's tool count.
- [ ] Write `api/tests/unit/agent_tools/test_rollup_augmentations.py` (returns text under `"consolidation"`; prompt carries focus + all summaries + marker-preservation language; unreachable-model → `{"error": ...}`).

## Command helpers

- [ ] Add `consolidation_call_bound(item_count: int, group_size: int) -> int` to `api/src/mythrix/agent/commands/augment.py`.
- [ ] Add `consolidation_progress_message(level: int, rank: int, of: int) -> str` to the same module.
- [ ] Extend `render_plan(...)` with keyword-only `consolidation_group_size: int = 8`; replace the fixed "plus one to consolidate them" clause with the computed, pluralized figure. Verify no "up to" phrasing is introduced.
- [ ] Table-driven unit tests for `consolidation_call_bound` in `api/tests/unit/test_agent_commands_augment.py` (boundary at `item_count == group_size`, just-over, two-level case).
- [ ] Update existing `render_plan(...)` call sites/assertions in `test_agent_commands_augment.py` for the new consolidation-count wording; add an assertion that "up to" is absent for both small-N and large-N cases.

## Node orchestration

- [ ] Add `_consolidate(tools, focus, augmentations, group_size) -> tuple[dict, int]` to `api/src/mythrix/agent/graph/nodes/augment.py`, per plan.md's algorithm (lazy `rollup_augmentations` lookup, level-driven tool selection, streamed progress message per non-final invocation).
- [ ] Replace the direct `consolidate_augmentations` invocation in `run_augment_node` (current lines ~150–161) with a call to `_consolidate`; use its returned call count in the `augment done: ... model_calls=%d` log line.
- [ ] Add `consolidation_group_size` keyword-only parameter to `run_augment_node` and `plan_augment_node`; thread into `render_plan` and `_consolidate`.
- [ ] Update the module docstring and `run_augment_node`'s docstring to describe the bounded-but-variable call count (reference ADR-016) instead of "N+1".

## Wiring

- [ ] Add `augment_consolidation_group_size: int` parameter to `compile_agent_graph` in `api/src/mythrix/agent/graph/builder.py`; thread into both `plan_augment` and `run_augment` node lambdas; extend the docstring.
- [ ] Pass `augment_consolidation_group_size=settings.augment_consolidation_group_size` at the `compile_agent_graph(...)` call site in `api/src/mythrix/api/dependencies.py`.
- [ ] Add `AUGMENT_CONSOLIDATION_GROUP_SIZE = 8` to `api/tests/unit/graph_helpers.py`; thread as an overridable kwarg through `compile_graph(...)`.

## Multi-level integration tests

- [ ] Add a multi-level test (in or alongside `api/tests/unit/test_agent_turn_service.py`) forcing two reduce levels via a small `consolidation_group_size`, with fakes for `read_region`, `augment_passage`, `consolidate_augmentations`, and `rollup_augmentations`. Assert: markers scripted into an intermediate fake rollup survive to the terminal reply and validate; a marker dropped by a scripted rollup is absent from the final reply and does not spuriously validate; the expected number of progress `message` events precede the terminal event with no accompanying `instruction`.
- [ ] Add a test confirming a small-N run never requires `rollup_augmentations` to be present in `node_tools`.
- [ ] Confirm the existing augmentation tests in `test_agent_turn_service.py` (N=2) pass unmodified.

## Spec and ADR

- [ ] Update `specs/interfaces/augmentation.md`: FR-AU-20, FR-AU-21 rewritten; new FR-AU-39 (marker preservation), FR-AU-40 (group size configurability), FR-AU-41 (reduce-phase streaming); FR-AU-37 wording fix.
- [ ] Add `specs/architecture-decisions/adr-016-hierarchical-map-reduce-augmentation-consolidation.md` per plan.md's outline, explicitly scoping what it supersedes from ADR-015.

## Finish

- [ ] `ruff check . && ruff format .` clean.
- [ ] `pytest api/tests/unit` green.
- [ ] Manual verification per plan.md's Verification section (small-N run behaves as before; forced large-N run streams multiple consolidation progress messages and produces a valid final reply).
