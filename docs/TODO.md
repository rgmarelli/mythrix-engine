# TODO

## Bugs & Fixes

- **Model not properly handling context sometimes.**
    ```   
    Example: Retrieve The Sun in Rider Waite

    - Input: Explain passages in relation to the concept of laughter

    - Output: It appears that there is no specific tarot card or sign associated with the concept of humor in the Rider-Waite tradition. Let's attempt to fetch signs related to laughter from any available traditions within the Tarot semiotic system.

    Let's start by fetching these signs.
    ``` 

- **Querying: Filter** seems to not work anymore; at least when running a query, it returns "standalone" results.

- **Augmentation: Increasing `augment_max_regions` to 50 produces bad consolidation.** Understand max value for `augment_max_regions` and see if we can somehow tune the consolidation phase. Testing showed that max=20 produces accurate results.


## Features
- **Augmentation: Add links in `/augmentation` output to navigate regions.** Clicking `[Rn]` should make the UI focus on the `Rn` region.

- **`/summarize` ignores Add Context expansion.** Tapping "Add Context" in `HotspotDetailPanel` only extends local component state (`handleAddContext` → `fetchSegments` → `mergeSegments`, `web/src/components/HotspotDetailPanel.tsx:93`); it never reaches the backend. `/summarize`'s rewrite (`turn_service.py:_rewrite_summarize_command`) still scopes to `context.region_id`/`locator`, so the agent summarizes only the original hotspot region, not the wider range the user just loaded on screen. Needs a Specify pass (`specs/tmp/`) before implementation — likely either sending the expanded ordinal range up with the `/summarize` request, or having the backend directive reflect what's currently rendered.

- **Add context not working for Bahir when there are no gaps to fill.** It says: "Full context loaded."
