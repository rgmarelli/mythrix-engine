# TODO

## Bugs & Fixes

* [ ] **Model not properly handling context sometimes.**
  ```text   
  Example: Retrieve The Sun in Rider Waite

  - Input: Explain passages in relation to the concept of laughter

  - Output: It appears that there is no specific tarot card or sign associated with the concept of humor in the Rider-Waite tradition. Let's attempt to fetch signs related to laughter from any available traditions within the Tarot semiotic system.

  Let's start by fetching these signs.
  ``` 

* [ ] **Refactor: stream_chat_turn**. The current design is overly coupled with command handling (e.g., session.pending_query = result.pending_query, session.pending_augmentation = result.pending_augmentation).

## Features
* [ ] **`/summarize` ignores Add Context expansion.** Tapping "Add Context" in `HotspotDetailPanel` only extends local component state (`handleAddContext` → `fetchSegments` → `mergeSegments`, `web/src/components/HotspotDetailPanel.tsx:93`); it never reaches the backend. `/summarize`'s rewrite (`turn_service.py:_rewrite_summarize_command`) still scopes to `context.region_id`/`locator`, so the agent summarizes only the original hotspot region, not the wider range the user just loaded on screen. Needs a Specify pass (`specs/tmp/`) before implementation — likely either sending the expanded ordinal range up with the `/summarize` request, or having the backend directive reflect what's currently rendered.

* [ ] **Add context not working for Bahir when there are no gaps to fill.** It says: "Full context loaded."

* [ ] **Augmentation: Clarify context.** Augmentation uses a context expansion feature that mentions fragments that can be "hidden" from the user. This is confusing, so we need to add clarification in the UI.

* [ ] **Remove dimmed functionality in UI.** Remove dimmed functionality in UI. i.e: (dimmed = matched but outside current filter)

# Improvement
* [ ] **Architecture: Improve session management.** Enhance session management scalability by adopting a stateless design. This can be achieved either by delegating session handling to the client side or integrating a centralized shared store (e.g., Redis). Avoid local, in-memory session persistence.
