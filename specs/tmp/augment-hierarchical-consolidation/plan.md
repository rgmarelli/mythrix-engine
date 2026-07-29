# Plan: Hierarchical consolidation for `/augment`

Grounds spec.md's requirements in the actual codebase. Supersedes, for consolidation only, the "exactly one further generation-model invocation" / "exactly N+1" clauses of ADR-015 and FR-AU-20/FR-AU-21 — everything else in ADR-015 (node-only tool split, region-identity-only trust surface, per-region streaming, narrowed history recording, sequential execution) is unaffected.

## Design decision: two node-only tools, split by input shape

- `consolidate_augmentations` (`agent/tools/consolidate_augmentations.py`, existing, unchanged) — used only at the first consolidation level. Given raw, individually `[R#]`-labeled augmentation texts; its prompt (`render_consolidation_prompt`) instructs citing from that label vocabulary.
- `rollup_augmentations` (new) — used at every level above the first. Given already-synthesized summaries that already embed `[R#]` markers produced by a lower level, with no label of their own. Its prompt (`render_rollup_prompt`) instructs carrying every embedded marker forward verbatim and inventing none.

Rejected: reusing `consolidate_augmentations` for both. Its prompt's citation contract ("cite the regions supporting each claim by their label... never cite a label that does not appear above") depends on every input having exactly one label that *is* the call's citation vocabulary. Feeding it multi-marker summaries either forces a synthetic per-group label the citation validator (`agent/citations.py`'s `_MARKER_PATTERN`, which only recognizes `G\d+|S\d+|C\d+|R\d+`) doesn't recognize, or invites the model to treat a whole summary as one new claim and drop the markers embedded in it — breaking FR-6/FR-7.

## Algorithm

New helper in `agent/graph/nodes/augment.py`, replacing the single `consolidate_augmentations` invocation currently at lines 150–161 of `run_augment_node`:

```python
def _consolidate(
    tools: list, focus: str, augmentations: tuple[RegionAugmentation, ...], group_size: int
) -> tuple[dict, int]:
    writer = get_stream_writer()
    consolidate = _tool_by_name(tools, "consolidate_augmentations")
    items: list[str] = [a.text for a in augmentations]
    labels: list[str] = [a.label for a in augmentations]
    calls = 0
    level = 1

    while len(items) > group_size:
        rollup = _tool_by_name(tools, "rollup_augmentations")
        batches = list(itertools.batched(items, group_size))
        next_items: list[str] = []
        for rank, batch in enumerate(batches, start=1):
            calls += 1
            if level == 1:
                result = consolidate.invoke({
                    "focus": focus,
                    "augmentations": [{"label": l, "augmentation": t} for l, t in zip(labels, batch)],
                })
            else:
                result = rollup.invoke({"focus": focus, "summaries": list(batch)})
            if "error" in result:
                return result, calls
            next_items.append(result["consolidation"])
            writer({"message": consolidation_progress_message(level, rank, len(batches))})
        items, labels, level = next_items, [], level + 1

    calls += 1
    tool = consolidate if level == 1 else _tool_by_name(tools, "rollup_augmentations")
    final = (
        tool.invoke({"focus": focus, "augmentations": [{"label": l, "augmentation": t} for l, t in zip(labels, items)]})
        if level == 1
        else tool.invoke({"focus": focus, "summaries": items})
    )
    return final, calls
```

Correctness properties this relies on:

- **Fast path is exactly today's behavior.** When N ≤ `group_size`, the `while` loop body never executes; the function falls straight to the final call at `level == 1`, i.e. one `consolidate_augmentations` invocation over the raw augmentations — identical to the code path being replaced.
- **`rollup_augmentations` is looked up lazily**, only inside the loop body — a run that never exceeds `group_size` never needs the tool to exist in the tools list.
- **Labels only exist at level 1.** `labels` is reset to `[]` once a level completes; which tool is called is driven by `level`, never by inspecting the batch's content, so there is no ambiguity about which prompt contract applies.
- Whenever the loop body runs, `len(items) > group_size` guarantees `len(batches) >= 2` (batching `k > g` items into groups of `g` always yields `ceil(k/g) >= 2`), so a group of exactly one item is never handed to `rollup_augmentations` mid-loop.
- Requires `itertools.batched` (Python 3.12+; `pyproject.toml` already requires `>=3.12`).
- `augment_consolidation_group_size` must be `>= 2` — at 1 the loop never shrinks `items` and never terminates.

## File-by-file changes

**`api/src/mythrix/core/config.py`**
- Add `augment_consolidation_group_size: int = Field(default=8, ge=2)` (needs `pydantic.Field`, not currently imported in this file — add the import).
- Docstring paragraph beside `augment_max_regions`'s, explaining: the FR it serves (FR-2), why 8 (matches the shape of a bounded batch that stays well inside `generation_num_ctx=8192` regardless of how large `augment_max_regions` is set), and the `>= 2` floor (a group of 1 never reduces).

**`api/src/mythrix/agent/prompts.py`**
- Add `render_rollup_prompt(focus: str, summaries: tuple[str, ...]) -> str`. Same focus-framing convention as `render_consolidation_prompt`. States plainly that the inputs are already-synthesized analyses, each already citing specific regions via `[R#]` markers embedded in its own text. Instructs synthesizing across them into one further analysis of the focus. Separately and explicitly: preserve every `[R#]` marker exactly as it appears, verbatim; never invent one; never renumber or merge two into one; if summaries are shown with a positional label for readability, that label is not a citation marker and must not appear in the output.

**`api/src/mythrix/agent/tools/rollup_augmentations.py`** (new)
```python
def build_rollup_augmentations_tool(chat_client: ChatClient):
    @tool
    def rollup_augmentations(focus: str, summaries: list[str]) -> dict:
        """Combine several already-synthesized analyses — each already citing
        regions via [R#] markers embedded in its text — into one further
        synthesis, preserving every such marker verbatim. Reachable only from
        a deterministic node."""
        return _generated(chat_client, render_rollup_prompt(focus, tuple(summaries)), "consolidation")
    return rollup_augmentations
```
Returns under the same `"consolidation"` key as the leaf tool so `_consolidate`'s result handling is uniform.

**`api/src/mythrix/agent/tools/__init__.py`**
- Import and register `build_rollup_augmentations_tool(chat_client)` in `node_tools`.
- Update the module docstring's "three reachable only from a deterministic node" to four.

**`api/src/mythrix/agent/graph/nodes/augment.py`**
- Add `_consolidate` (above) and use it in `run_augment_node` in place of the current direct `consolidate_augmentations` invocation.
- `run_augment_node(state, tools, *, max_regions: int, consolidation_group_size: int)` and `plan_augment_node(state, *, max_regions: int, consolidation_group_size: int)` — new keyword-only parameter on both, since the plan turn now needs the group size to compute the call count shown to the user.
- Update the module docstring and `run_augment_node`'s own docstring: both currently state generation calls total "N+1"; replace with a reference to the bounded, deterministic-but-variable count (ADR-016).
- `logger.info("augment done: ...")`'s `model_calls=%d` becomes `len(augmentations) + consolidation_calls`, using the count `_consolidate` returns.

**`api/src/mythrix/agent/commands/augment.py`**
- Add `consolidation_call_bound(item_count: int, group_size: int) -> int`, pure arithmetic mirroring `_consolidate`'s batching (used both to compute the plan-time figure and unit-tested directly):
  ```python
  def consolidation_call_bound(item_count: int, group_size: int) -> int:
      if item_count <= 1:
          return item_count
      calls, items = 0, item_count
      while items > group_size:
          items = -(-items // group_size)  # batches produced this level
          calls += items
      return calls + 1
  ```
- Add `consolidation_progress_message(level: int, rank: int, of: int) -> str`, e.g. `f"Consolidated group {rank}/{of} (pass {level})"`.
- `render_plan(focus, supplied, augmenting, augmentation_id, *, consolidation_group_size: int = 8)` — new keyword-only parameter with a literal default (this module stays free of a `Settings` import). Replaces the fixed "plus one to consolidate them" clause with the computed, pluralized figure from `consolidation_call_bound`. Must not introduce the phrase "up to" anywhere in the rendered string — `test_the_plan_states_one_count_when_nothing_is_truncated` (`api/tests/unit/test_agent_commands_augment.py`) asserts that phrase's absence over the whole plan text, not just the region-count clause.

**`api/src/mythrix/agent/graph/builder.py`**
- `compile_agent_graph(..., augment_max_regions: int, augment_consolidation_group_size: int)` — new parameter threaded into both the `plan_augment` and `run_augment` node lambdas alongside `augment_max_regions`.
- Extend the docstring's `augment_max_regions` paragraph with a parallel sentence for the new parameter.

**`api/src/mythrix/api/dependencies.py`**
- Add `augment_consolidation_group_size=settings.augment_consolidation_group_size` to the existing `compile_agent_graph(...)` call, mirroring `augment_max_regions=settings.augment_max_regions`.

**`api/tests/unit/graph_helpers.py`**
- Add `AUGMENT_CONSOLIDATION_GROUP_SIZE = 8` and thread it through `compile_graph(...)` as an overridable kwarg passed to `compile_agent_graph`, mirroring `AUGMENT_MAX_REGIONS`. This is the single choke point keeping every other `test_agent_turn_service.py` call site compiling unmodified.

## Spec document updates (not this feature's spec.md — the shipped interface spec)

**`specs/interfaces/augmentation.md`**
- FR-AU-20: replace "exactly one further generation-model invocation consolidates them" with the bounded map-reduce description (batches of at most `augment_consolidation_group_size`; repeated until one result remains; no invocation above the first level sees raw passage text or the individual augmentations, only prior results).
- FR-AU-21: replace "exactly N+1 times... never more" with "N + C times for N augmented regions, where C is deterministic from N and `augment_consolidation_group_size`, never a function of model behavior, and equals 1 whenever N does not exceed the group size."
- New FR-AU-39 (marker preservation): a region marker is assigned once, at the first consolidation level, and never reassigned or renumbered; every invocation above that level carries forward, unchanged, whatever `[R#]` markers it is given, and has no vocabulary to invent new ones from.
- New FR-AU-40 (group size configurability): the number of results one consolidation invocation may be given is configurable and bounded by default, analogous to FR-AU-14, uniformly at every level.
- New FR-AU-41 (reduce-phase streaming): a run emits a chat message as each consolidation invocation other than its final one completes; no instruction accompanies it, since a group's result addresses no single region; the final consolidation invocation is not separately announced, since its result is the terminal reply.
- FR-AU-37: light wording fix, "the consolidation" → each consolidation invocation plus the run's total call count.

**New ADR** — `specs/architecture-decisions/adr-016-hierarchical-map-reduce-augmentation-consolidation.md`
- Context: `docs/TODO.md`'s finding (max=20 accurate, max=50 "bad consolidation"), traced to `render_consolidation_prompt` concatenating all N readings into one prompt.
- Decision: the map-reduce structure above, the two-tool split and why, `augment_consolidation_group_size`, reduce-phase streaming.
- Consequences: total generation calls become `N + C(N, group_size)`, not `N+1`; larger N now means a longer chain of sequential calls held on one open connection — the same unmitigated "no timeout anywhere" risk ADR-015 already named, now larger; two prompts/tools must now stay in sync with the marker-preservation invariant instead of one.
- Explicitly supersedes only ADR-015's "exactly N+1" / single-consolidation-call clauses; the rest of ADR-015 stands.
- Alternatives considered: overloading one tool for both levels (rejected, see Design decision above); raising `generation_num_ctx` instead of restructuring (rejected — the TODO's finding is about answer quality with more independent readings to synthesize, not fitting in a window); deterministic non-LLM merge above the first level (rejected — relocates the flat-dump problem one level up and loses synthesis quality, which is the actual complaint).

## Test impact

- **Unmodified**: `test_consolidate_augmentations.py` (tool untouched). `test_agent_turn_service.py`'s augmentation block — `_REGION_IDS` has 2 entries, well under the 8-item default group size, so `_consolidate`'s loop never runs and behavior is identical to today.
- **Updated**: `test_agent_commands_augment.py` gains assertions for the computed consolidation-count wording (small-N and large-N) and continued absence of "up to". `graph_helpers.py` gains the new kwarg.
- **New**:
  - `test_rollup_augmentations.py`, mirroring `test_consolidate_augmentations.py`'s shape: returns text under `"consolidation"`; prompt carries the focus and every summary; prompt contains marker-preservation instruction language; unreachable-model returns `{"error": ...}`.
  - Table-driven unit tests for `consolidation_call_bound` (boundary at `item_count == group_size`, just-over, and a two-level case).
  - A multi-level integration test (in or alongside `test_agent_turn_service.py`) using `graph_helpers.compile_graph(..., max_regions=<N>, consolidation_group_size=<small>)` with enough fake regions and a small group size to force two reduce levels, with fakes for `read_region`, `augment_passage`, `consolidate_augmentations`, and `rollup_augmentations`. Assert: markers scripted into an intermediate fake rollup result survive into the terminal reply and validate; a marker present at a leaf but *dropped* by a scripted rollup fake is absent from the final reply and does not spuriously validate; the expected number of progress `message` events appear before the terminal event, none carrying an `instruction`.
  - A test confirming `rollup_augmentations` is never looked up when N does not exceed the group size (a fake `node_tools` list omitting it must not break the run) — guards the lazy-lookup property against regression.
