# Tool-owned grounding ids

Grounding markers (`[G#]`, `[S#]`) let the agent's generated replies cite specific items returned by a tool call this turn, validated in code against tool results (`agent.md` FR-AG-06, `retrieval.md` FR-RT-04, [ADR-022](../../architecture-decisions/adr-022-tool-owned-opaque-grounding-ids.md)).

## Functional requirements

- FR-GID-01: Every citable item a tool returns (`get_sign`'s citations, `query_sign`'s segments, `fetch_segments`'s segments) carries a `grounding_id` field, assigned by the tool itself at the time it renders its result.
- FR-GID-02: A `grounding_id` is an opaque token, independently generated per item. It is never derived from the item's position within a tool result, a count of items returned so far in the turn, or any other value a caller could reconstruct without having received the tool result itself.
- FR-GID-03: A citation marker in a model-authored reply is valid only if it exactly matches a `grounding_id` present in a tool result from the current turn. No marker is valid by virtue of falling within an expected range or count.
- FR-GID-04: The generation model is instructed to copy a tool-supplied `grounding_id` verbatim when citing an item, and is never instructed to number, count, or otherwise construct a citation marker itself.
- FR-GID-05: Region markers (`[R#]`, `augmentation.md` FR-AU-30) are unaffected — they remain sequential and position-based, assigned by the deterministic augmentation node, not by this requirement set.

## Non-goals

- Making a `grounding_id` stable or reproducible across separate tool calls or turns for the same underlying item (e.g. the same segment fetched twice may receive two different ids).
- Changing region marker (`[R#]`) numbering or the augmentation flow.
