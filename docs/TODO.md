# TODO

## Bugs & Fixes

* [ ] **Model not properly handling context sometimes.**
  ```text   
  Example: Retrieve The Sun in Rider Waite

  - Input: Explain passages in relation to the concept of laughter

  - Output: It appears that there is no specific tarot card or sign associated with the concept of humor in the Rider-Waite tradition. Let's attempt to fetch signs related to laughter from any available traditions within the Tarot semiotic system.

  Let's start by fetching these signs.
  ``` 
* [ ] **Selecting an interpretant in the right panel only selects 1 matching segment instead of all.** Also, clicking again should remove the selection.

* [ ] **Review endpoints and definitions.**

* [ ] **Review /reload-signs endpoint.** Accepts a path parameter (security vulnerability).

* [ ] **Enforce MYTHRIX_GENERATION_MODEL env var on startup.** Prevent the server from starting if MYTHRIX_GENERATION_MODEL is missing or empty.

## Features
* [ ] **Augmentation: Clarify context.** Augmentation uses a context expansion feature that mentions fragments that can be "hidden" from the user. This is confusing, so we need to add clarification in the UI.

* [ ] **Add welcome message to Agent chat on application load.**

* [ ] **Add corpus ingestion user manual.**

# Improvement
* [ ] **Architecture: Improve session management.** Enhance session management scalability by adopting a stateless design. This can be achieved either by delegating session handling to the client side or integrating a centralized shared store (e.g., Redis). Avoid local, in-memory session persistence.

* [ ] **Adopt Conventional Commits specification across the repository.** 

* [ ] **Semiotic Models Update.**. Improve current sample models, add astrology models, and expand sources.

* [ ] **Update mythrix image in README.**.
