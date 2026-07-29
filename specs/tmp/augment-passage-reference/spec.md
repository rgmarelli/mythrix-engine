# Spec: Reference-grounded per-region augmentation

## Problem

`augment_passage`'s prompt (`render_augmentation_prompt`) gives the generation model a region's passage text and the run's focus, and nothing else — it is never told what passage it is reading. Observed in practice: the model recognizes the passage as scripture from its own training and states a reference for it inside the analysis text anyway, attributing it to the wrong book and verses (e.g. naming "Luke 1:76-79" for a passage the system itself attributes to a different source and locator). This is a fabricated claim delivered straight into reply text a user reads, and nothing downstream checks a generated augmentation against the region's actual, already-known source and locator.

## Goals

- The generation model producing a region's augmentation is given that region's true source and locator, so it has no need to infer or guess a reference from the passage text.
- The prompt explicitly instructs the model not to name, restate, or draw on outside/prior knowledge associated with that reference — it is given the reference to know what it is reading, not as license to answer from anything beyond the passage.
- The reference supplied to the model is exactly the source and locator already derived for that region by `read_region` (FR-AU-15) — never a second, independently-sourced value.

## Non-goals

- Changing how a region's source or locator is derived (`read_region`, FR-AU-15).
- Changing the consolidation prompt, `[R#]` labeling, or citation-marker validation (FR-AU-20, FR-AU-30, FR-AU-31).
- Detecting, stripping, or correcting a hallucinated reference after generation. The fix removes the model's motive and opportunity to guess; it does not filter its output.
- Reintroducing retrieval/search terms into the prompt. That remains excluded for the reason already documented (FR-AU-19): naming a matched term would invite the model to answer about the term instead of the run's focus. A reference is not a retrieval term and this change does not affect that exclusion.

## Functional requirements

- FR-1: Each augmented region's generation-model invocation is given that region's source and locator, in addition to its passage and the run's focus.
- FR-2: The source and locator given to the invocation are exactly the values `read_region` derived for that region (FR-AU-15) — the same values already used to label the region elsewhere in the run (e.g. the per-region progress line) — never a value from any other origin.
- FR-3: The invocation is instructed to use the reference only to know what passage it is reading, and explicitly not to discuss, restate, or rely on outside knowledge associated with that reference; the analysis must still answer from the passage's own text alone, unchanged from the existing grounding requirement.
