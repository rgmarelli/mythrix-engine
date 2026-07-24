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
