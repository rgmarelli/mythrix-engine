# Plan: Reference-grounded per-region augmentation

Grounds spec.md's requirements in the actual codebase. Amends FR-AU-19 only; every other FR in `specs/interfaces/augmentation.md` and all of ADR-015/ADR-016 are unaffected — `read_region` already derives source and locator (FR-AU-15), this plan only threads those two already-derived values one step further, into `augment_passage`'s own prompt.

## Design decision: pass `source`/`locator` as two plain strings, not a combined "reference"

`augment_passage` gains two new parameters, `source: str` and `locator: str`, mirroring the two fields `RegionAugmentation` and `read_region`'s return dict already keep separate (`agent/commands/augment.py`'s `RegionAugmentation.source`/`.locator`). `render_augmentation_prompt` combines them into one displayed line at render time.

Rejected: adding a single `reference: str` parameter built by the caller. It would introduce a new ad-hoc concept ("reference") with no type anywhere else in the codebase, and would push string formatting into `_augment_regions` instead of the one function whose job is prompt rendering. Keeping `source`/`locator` separate all the way to `render_augmentation_prompt` means the tool's only job is to pass through values it already has, and the "source — locator" display convention lives in exactly one place.

No new ADR. This is an addition to what an existing node-only tool's prompt is given, not a change to the deterministic-node architecture, the trust surface, message fabrication, or streaming behavior ADR-015/ADR-016 established.

## File-by-file changes

**`api/src/mythrix/agent/prompts.py`**
- `render_augmentation_prompt(text: str, focus: str) -> str` becomes `render_augmentation_prompt(text: str, focus: str, source: str, locator: str) -> str`.
- Adds a leading `Reference: {source} — {locator}.` line before the analytical-task line, reusing the same "source — locator" convention `region_done_message` (`agent/commands/augment.py:178`) already displays to users, so the same region reads the same way to the model as it does to a person.
- Adds an explicit instruction: the reference identifies the passage only; the model must not name, restate, or draw on outside/prior knowledge associated with that reference, and must continue to answer from the passage's own text alone.
- Docstring: replace "The retrieval terms are deliberately absent" reasoning with a clarification that a *reference* (source/locator) and a *retrieval term* are different things — the former is now included because it grounds identity, the latter remains excluded because naming it would redirect the answer toward the term instead of the focus (FR-AU-19, unchanged reasoning for that part).

**`api/src/mythrix/agent/tools/augment_passage.py`**
- `augment_passage(passage_text: str, focus: str, source: str, locator: str) -> dict`, forwarding the two new arguments straight into `render_augmentation_prompt`.
- Docstring: note the invocation is now told what passage it is reading, not just handed its text.

**`api/src/mythrix/agent/graph/nodes/augment.py`**
- `_augment_regions`'s call to `augment_passage.invoke(...)` (currently lines 278–280) adds `"source": region["source"], "locator": region["locator"]` — both already read off `region` two lines above for logging; no new lookup.

**`specs/interfaces/augmentation.md`**
- FR-AU-19: replace "given that region's passage and the run's focus" with "given that region's passage, its source and locator, and the run's focus. The invocation is instructed to use the reference to know what passage it is reading, not to draw on outside knowledge of it — it must still answer from the passage's text alone, or say so when the passage does not bear on the focus."

## Test impact

- **Updated** — `api/tests/unit/agent_tools/test_augment_passage.py`:
  - `test_augment_passage_prompt_carries_the_passage_and_the_focus` — invoke with `source`/`locator` too; unaffected otherwise.
  - `test_augment_passage_takes_no_retrieval_terms` — the asserted arg set `{"passage_text", "focus"}` becomes `{"passage_text", "focus", "source", "locator"}`. Docstring/name stay accurate: source/locator are the region's own derived identity, not a retrieval term.
  - New test: the prompt carries the given `source` and `locator` verbatim (e.g. asserts `"Douay-Rheims"` and `"Genesis 21:5–8"` both appear in the rendered prompt for those inputs).
  - New test: the prompt instructs against relying on outside knowledge of the reference (a substring assertion on the rendered prompt, mirroring how the existing "no retrieval terms" property is asserted elsewhere by content rather than structure).
- **Updated** — `api/tests/unit/test_agent_turn_service.py`'s augmentation block and any fake `augment_passage` tool used there: fakes matching on the tool's argument shape need the two new keys; behavior otherwise unaffected since the fakes' return values don't depend on them.
- **Unmodified**: `_consolidate`, `consolidate_augmentations`, `rollup_augmentations`, and their tests — consolidation is out of scope (spec.md non-goals).
