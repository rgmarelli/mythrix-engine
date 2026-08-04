# Plan: tool-owned grounding ids

Implements `spec.md` under [ADR-022](../../architecture-decisions/adr-022-tool-owned-opaque-grounding-ids.md).

## Approach

Each tool that returns citable items assigns a `grounding_id` to each one at render time, using a shared helper. Validation reads that field directly instead of reconstructing a positional count. No shared state crosses tool calls — ids are independently generated per item, so no `Command`/`InjectedState` machinery is needed on any tool.

## Changes

1. **`api/src/mythrix/agent/tools/_shared.py`** — add `_new_grounding_id(prefix: str) -> str`, returning `f"{prefix}{uuid4().hex[:6]}"` (mirrors `commands/augment.py::new_augmentation_id`'s `uuid4()` convention). Call it from:
   - `_render_graph_facts`: each `citations` entry gets `"grounding_id": _new_grounding_id("G")`.
   - `_render_regions`: each `segments` entry (per region) gets `"grounding_id": _new_grounding_id("S")`.

2. **`api/src/mythrix/agent/tools/fetch_segments.py`** — revert the in-progress `Command`/`InjectedState`/`InjectedToolCallId`/`citation_count` proof of concept back to a plain `@tool` function returning `list[dict]`; add `"grounding_id": _new_grounding_id("S")` to each segment dict.

3. **`api/src/mythrix/agent/graph/state.py`** — remove `citation_count: Annotated[int, operator.add]` and the `operator` import; no longer needed once ids are independently generated.

4. **`api/src/mythrix/agent/runner.py`** — remove `"citation_count": 0` from the initial state dict in `stream_turn`.

5. **`api/src/mythrix/agent/turn_service.py`** — in `_build_valid_marker_ids`, replace the `g_count`/`s_count` positional-counting branches for `get_sign` and `query_sign` with direct reads of each item's `grounding_id`; keep the `fetch_segments` branch's existing `grounding_id` read (drop the dead commented-out line); leave the `augment_regions`/`r_count` branch untouched. Remove the stray `print("============= HACKED =============")` debug line in `_ungrounded_markers`.

6. **`api/src/mythrix/agent/citations.py`** — widen `_MARKER_PATTERN`/`_STRIP_PATTERN` so `G`/`S`/`C` accept a hex-alnum suffix (`[0-9a-f]+`) instead of digits only; `R` stays `\d+`. No change to `extract_markers`/`strip_markers`/`strip_all_markers`/`find_invalid_markers` logic.

7. **`api/src/mythrix/agent/prompts.py`** — restore `SYSTEM_PROMPT` to its committed `HEAD` content, then replace only the two citation-indexing lines with one line stating each tool result item carries its own grounding id to copy verbatim. Delete the unused `SYSTEM_PROMPT_TEST` variable entirely.

8. **Tests**:
   - `api/tests/unit/agent_tools/test_get_sign.py` — assert `source`/`locator` plus a non-empty `grounding_id`, not an exact-equality citations list.
   - `api/tests/unit/agent_tools/test_fetch_segments.py` — assert each segment carries a non-empty `grounding_id`; tool is invoked the same plain way as before (POC's injected-arg signature is gone).
   - `api/tests/unit/test_agent_turn_service.py` — fixture `get_sign`/`fetch_segments` tools emit fixed `grounding_id` values per test case; scripted `AIMessage` replies cite those fixed ids instead of `[G1]`/`[S1]`.

## Out of scope

- `[R#]` region marker numbering (`commands/augment.py`, `graph/nodes/augment.py`) — unchanged.
- `specs/interfaces/agent.md`/`augmentation.md` FR wording — no changes needed; FR-AG-06 and FR-AU-30 already describe behavior consistent with this change.
