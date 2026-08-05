# Spec: citation fact-checker

References: ADR-025, ADR-006, ADR-022. Extends `specs/interfaces/agent.md` FR-AG-06.

## Functional requirements

- **FR-FC-01**: The model-driven conversational turn's final reply (no further tool calls) is not itself asked to carry a citation marker. The generation model's system prompt contains no instruction about grounding ids.
- **FR-FC-02**: When a turn's tool calls returned at least one citable item (a `get_sign` citation, or a `query_sign`/`fetch_segments` segment), the final reply is split into sentences and passed, together with the full text of every citable item returned this turn, to a separate fact-checking model call before the turn ends.
- **FR-FC-03**: The fact-checking call receives a pre-filled document with one entry per sentence — each entry already carrying its own position and text — and the evidence, and is asked to complete the document rather than generate one from scratch. It returns a classification: for each entry, whether its sentence is supported, unsupported, or states no factual claim, and if supported, which evidence item id(s) support it. Every entry the call was given must come back with a classification; none may be omitted, added, reordered, or renamed.
- **FR-FC-04**: The fact-checking call's response is verified structurally, not by comparing reproduced text: it must be a well-formed classification (a valid response format, each entry naming a sentence that exists and a supported/unsupported/no-claim value). An entry that fails this check is discarded individually; a response that cannot be read as a classification at all is discarded entirely and the reply falls back to FR-FC-06. An evidence item id is matched to the evidence this turn actually has irrespective of incidental formatting the fact-checking call's response wraps it in.
- **FR-FC-05**: A turn whose tool calls returned no citable item (including a turn that called only enumeration tools, or no tools at all), or whose reply has no sentences to classify, is not sent to the fact-checking call. Its reply stands unmodified.
- **FR-FC-06**: The fact-checking call is not retried, and its failure (the call could not be completed, or its response fails FR-FC-04's check) never replaces the reply with a rejection message. It falls back to the original reply, unmodified.
- **FR-FC-07**: A grounding score — the count of sentences classified as supported by a genuine evidence item id, divided by the count of all classified sentences — is computed from the fact-checking call's classification after FR-FC-04's check passes. A sentence classified as supported but naming no evidence item id that actually exists in this turn's evidence counts as not supported. When no sentence was classified at all, no score is computed.
- **FR-FC-08**: The reply returned to the user is always the original reply's own text, verbatim — the fact-checking call's classification is never merged into or used to construct the displayed reply's text.
- **FR-FC-09**: When a grounding score was computed (FR-FC-07), the reply returned to the user has a line appended after the reply text, reporting the score as a whole-number percentage. No such line is appended when no score was computed, or when the fact-checking call's response was discarded (FR-FC-04/FR-FC-06).
- **FR-FC-10**: `/augment`'s reply (region markers, `specs/interfaces/augmentation.md` FR-AU-30) is not affected by this mechanism; its existing validation is unchanged.
- **FR-FC-11**: The logic that renders the fact-checking prompt and makes the fact-checking call accepts a list of evidence items (each an id, a source, a locator, and text) and a list of sentences, as plain values — it has no dependency on the conversational graph's state shape or on how a caller obtained those values.

## Non-goals

- Extending this mechanism to `/summarize` or `/augment`'s own generated text. (The fact-checking logic is built reusable for that per FR-FC-11, but no call site for either command is added by this spec.)
- Changing anything about how a grounding id itself is generated (ADR-022, unaffected).
- Making individual citations (evidence item ids or per-sentence supported/unsupported classification) visible to the user — only the aggregate score is.
- A configurable minimum-score gate that blocks or alters a reply below some threshold.
- Reconstructing or editing the reply's text from the sentences it was split into for classification — the split exists only to give the fact-checking call a way to refer to a sentence by position; the displayed reply is always the original, unsplit text (FR-FC-08).
