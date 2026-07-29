# TODO

- **`/summarize` ignores Add Context expansion.** Tapping "Add Context" in
  `HotspotDetailPanel` only extends local component state
  (`handleAddContext` → `fetchSegments` → `mergeSegments`,
  `web/src/components/HotspotDetailPanel.tsx:93`); it never reaches the
  backend. `/summarize`'s rewrite (`turn_service.py:_rewrite_summarize_command`)
  still scopes to `context.region_id`/`locator`, so the agent summarizes only
  the original hotspot region, not the wider range the user just loaded on
  screen. Needs a Specify pass (`specs/tmp/`) before implementation — likely
  either sending the expanded ordinal range up with the `/summarize` request,
  or having the backend directive reflect what's currently rendered.

- **"Run this query" button is broken** it shows a horrible circle instead of a button

- **Add context not working for Bahir when there are no gaps to fill** It says: full context loaded.

- **List tradition not working any more** It invents: Raider-Waite-Smith. Seems I have a fix changing tool output to just return slug.

- **Model not properly handling context sometimes**

```   
Example: Retrieve The Sun in Rider Waite

- Explain passages in relation to the concepto of laughter

It appears that there is no specific tarot card or sign associated with the concept of humor in the Rider-Waite tradition. Let's attempt to fetch signs related to laughter from any available traditions within the Tarot semiotic system.

Let's start by fetching these signs.
``` 

