# Spec: in-graph citation retry

References: ADR-023, ADR-022, ADR-006. Extends `specs/interfaces/agent.md` FR-AG-06.

## Functional requirements

- **FR-CR-01**: When the model-driven conversational turn's final reply (no further tool calls) contains a citation marker that does not match a `grounding_id` this turn's tool results actually returned, the turn is not immediately rejected. The model is given a bounded number of further attempts to correct it.
- **FR-CR-02**: Each retry attempt is preceded by a message naming the specific invalid marker(s) found and instructing the model to answer again using only the valid grounding ids from this turn's tool results.
- **FR-CR-03**: The number of retry attempts is bounded by a configurable limit. Once exhausted, the turn falls back to the existing citation-failure reply.
- **FR-CR-04**: A turn where every tool call was a plain listing call (`list_signs`/`list_traditions`/`list_semiotic_systems` — no citable content) is never subject to citation validation or retry.
- **FR-CR-05**: `/augment`'s reply (region markers, FR-AU-30) is not affected by this retry mechanism; its existing validation is unchanged.
- **FR-CR-06**: A reply that self-corrects within the retry budget is delivered to the user as if it had been correct on the first attempt — no trace of the invalid intermediate attempt(s) or the corrective message(s) is visible in the delivered reply.

## Non-goals

- Extending the retry mechanism to `/augment`'s consolidation reply.
- Changing the shape or validation rules of `[R#]` region markers.
- Changing anything about how a grounding id itself is generated (ADR-022, unaffected).
