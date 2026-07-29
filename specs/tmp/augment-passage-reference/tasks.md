# Tasks: Reference-grounded per-region augmentation

## Prompt

- [ ] Change `render_augmentation_prompt` in `api/src/mythrix/agent/prompts.py` to take `source: str, locator: str` in addition to `text`/`focus`; render a leading `Reference: {source} — {locator}.` line; add the "identify the passage only, do not draw on outside knowledge of the reference" instruction; update the docstring to distinguish reference (now included) from retrieval terms (still excluded).

## Tool

- [ ] Change `augment_passage` in `api/src/mythrix/agent/tools/augment_passage.py` to accept `source: str, locator: str`, forwarded to `render_augmentation_prompt`; update its docstring.

## Node wiring

- [ ] In `_augment_regions` (`api/src/mythrix/agent/graph/nodes/augment.py`), pass `"source": region["source"], "locator": region["locator"]` into the `augment_passage.invoke(...)` call.

## Tests

- [ ] `api/tests/unit/agent_tools/test_augment_passage.py`:
  - Update `test_augment_passage_prompt_carries_the_passage_and_the_focus` to invoke with `source`/`locator`.
  - Update `test_augment_passage_takes_no_retrieval_terms`'s asserted arg set to `{"passage_text", "focus", "source", "locator"}` (keep the test name/docstring — source/locator are derived identity, not a retrieval term).
  - Add a test asserting the rendered prompt carries the given `source` and `locator` verbatim.
  - Add a test asserting the prompt instructs against relying on outside knowledge of the reference.
- [ ] `api/tests/unit/test_agent_turn_service.py`: update the fake `augment_passage(passage_text, focus)` (line ~650) to accept `source`, `locator`; confirm existing augmentation-block assertions still pass.

## Spec

- [ ] Update FR-AU-19 in `specs/interfaces/augmentation.md` per plan.md.

## Finish

- [ ] `ruff check . && ruff format .` clean.
- [ ] `pytest api/tests/unit` green.
- [ ] Manual check: run `/augment` against a region whose true source/locator is known, confirm the model's augmentation text no longer states a different book/verse.
