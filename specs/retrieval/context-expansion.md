# Post-retrieval context

How verbatim, non-matching segments are progressively loaded around a hotspot's ([ranking.md](ranking.md)) matched segments, without affecting retrieval or ranking. Surfaced in the web viewer via the detail panel's **Add Context** action ([web-viewer.md](../interfaces/web-viewer.md)).

## Vocabulary

- **matched segment**: A hotspot segment that carried at least one interpretant match — the only segments the detail panel shows before any context is added.
- **context segment**: A verbatim segment from the same source, loaded into the detail panel on demand, that carried no interpretant match.
- **internal gap**: A non-matching segment whose ordinal lies strictly between a hotspot's lowest and highest matched ordinal, absent from the hotspot as returned.
- **leading edge / trailing edge**: The lowest-ordinal and highest-ordinal segment currently loaded in a hotspot's detail panel (matched or context).
- **chapter boundary**: The first/last segment of the structural section (`Segment.section`, e.g. a scripture chapter or a numbered section) that an edge segment belongs to. A source that declares no such structure has no chapter boundary; its only bounds are the source's first and last segment.

## Functional requirements

- FR-CE-01: The hotspot detail panel provides an **Add Context** action that loads additional verbatim segments from the same source as the hotspot and displays them interleaved, in structural (ordinal) order, with the hotspot's existing segments. Context segments are visually distinguished from matched segments.
- FR-CE-02: An activation first fills every remaining internal gap — each non-matching segment whose ordinal lies strictly between the current leading and trailing edges but is not yet loaded — so the loaded span reads as one contiguous, gap-free sequence of segments.
- FR-CE-03: When no internal gap remains, an activation extends the loaded span by one segment before the current leading edge and one segment after the current trailing edge, subject to FR-CE-04/FR-CE-05.
- FR-CE-04: When the source declares a chapter/section structure, each edge stops at its own chapter boundary: the leading edge never loads a segment from the previous chapter, and the trailing edge never loads a segment from the next chapter.
- FR-CE-05: When the source declares no chapter/section structure, each edge extends toward the source's first / last segment and stops there.
- FR-CE-06: The two edges advance independently. An activation extends every edge that can still extend; an edge already at its bound contributes nothing while the other edge continues. The action remains available while any edge can still extend or any internal gap remains.
- FR-CE-07: The action is disabled (and visibly indicates that no further context is available) once no internal gap remains and both edges have reached their bounds.
- FR-CE-08: Context is drawn only from the same source as the hotspot. Expansion never crosses into another source or another hotspot.
- FR-CE-09: Loaded context is scoped to the individual hotspot. Selecting a different hotspot presents that hotspot's own matched segments with no context carried over; a new query resets all expansion.
- FR-CE-10: Context segments display their verbatim text and structural locator with no client-side truncation, consistent with [ranking.md](ranking.md) FR-RK-08 / [web-viewer.md](../interfaces/web-viewer.md) FR-WEB-03. Interpretant chips continue to anchor to and scroll to their matched segments after context is loaded; context segments are never chip targets.
- FR-CE-11: The backend exposes retrieval of a source's segments by structural coordinate — a contiguous ordinal range within one source — returning each segment's verbatim text, structural locator, ordinal, and section, executed through the existing stores without running a similarity query. This is sufficient for the client to render context and to determine chapter boundaries (FR-CE-04) and source ends (FR-CE-05).
- FR-CE-12: A context-load request that fails returns a distinct, client-visible error without altering or clearing the displayed hotspot or the current query result.

## Non-goals

- Merging multiple hotspots of the same source into one continuous reading view, crossing a chapter/section boundary during context expansion, persisting a hotspot's expansion state across queries or browser reloads, re-running a similarity search to fetch context, or a one-click affordance to load an entire chapter/source at once; context segments never affect retrieval, ranking, convergence scoring, or facet counts.
