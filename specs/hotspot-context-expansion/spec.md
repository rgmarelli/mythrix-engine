# Hotspot Context Expansion — Spec

## Problem

The web viewer's hotspot detail panel shows only a hotspot's match-carrying
segments (each matched segment once, deduped by ordinal, per master FR46). The
non-matching segments that fall *between* matches, and the segments
*surrounding* the hotspot, are absent — so a researcher cannot read a match in
its immediate textual context without leaving the tool. The on-demand AI
summary (master FR54) is likewise limited to the matched segments and cannot
summarize the wider passage a researcher may want to reason over.

## Vocabulary

- **hotspot** — the web viewer's display term for a ranked region (master spec).
- **matched segment** — a hotspot segment that carried at least one interpretant
  match; the only segments the panel shows before any context is added.
- **context segment** — a verbatim segment from the same source, loaded into the
  panel on demand, that carried no interpretant match.
- **internal gap** — a non-matching segment whose ordinal lies strictly between
  the hotspot's lowest and highest matched ordinal, absent from the hotspot as
  returned.
- **leading edge / trailing edge** — the lowest-ordinal and highest-ordinal
  segment currently loaded in the panel (matched or context).
- **chapter boundary** — the first / last segment of the structural section
  (`Segment.section`, e.g. a scripture chapter or a numbered section) that an
  edge segment belongs to. A source that declares no such structure has no
  chapter boundary; its only bounds are the source's first and last segment.

## Goals

- An in-panel **Add Context** control that progressively loads surrounding
  verbatim context around a hotspot's matched segments, drawn from the same
  source, without issuing a new query.
- Expansion bounded by the enclosing chapter/section where the source declares
  one, and bounded only by the source's ends where it does not.
- An AI summary scoped to whatever context is currently loaded in the panel,
  not only the originally matched segments.

## Non-goals

- Merging or stitching multiple hotspots of the same source into one continuous
  reading view. Expansion is scoped to a single hotspot's detail panel; other
  hotspots are untouched.
- Crossing a chapter/section boundary. When a source declares chapters,
  expansion never pulls in a segment from an adjacent chapter.
- Persisting a hotspot's expansion state across queries, across a browser
  reload, or when navigating away from and back to the hotspot.
- Any change to retrieval, ranking, convergence scoring, facets, or what counts
  as a match. Context segments are read-only display context; they are never
  matches, are never counted in convergence, and never affect facet counts.
- Re-running a similarity search to fetch context. Context is retrieved by
  structural coordinate, not by embedding similarity.
- A one-click "load the whole source/chapter at once" affordance. The whole
  enclosing chapter (or whole source) is reached only through repeated
  activations.

## Functional requirements

- FR1: The hotspot detail panel provides an **Add Context** action that loads
  additional verbatim segments from the same source as the hotspot and displays
  them interleaved, in structural (ordinal) order, with the hotspot's existing
  segments. Context segments are visually distinguished from matched segments.
- FR2: An activation first fills every remaining **internal gap** — each
  non-matching segment whose ordinal lies strictly between the current leading
  and trailing edges but is not yet loaded — so the loaded span reads as one
  contiguous, gap-free sequence of segments.
- FR3: When no internal gap remains, an activation extends the loaded span by
  one segment before the current leading edge and one segment after the current
  trailing edge, subject to FR4/FR5.
- FR4: When the source declares a chapter/section structure, each edge stops at
  its own **chapter boundary**: the leading edge never loads a segment from the
  previous chapter, and the trailing edge never loads a segment from the next
  chapter.
- FR5: When the source declares no chapter/section structure, each edge extends
  toward the source's first / last segment and stops there.
- FR6: The two edges advance independently. An activation extends every edge
  that can still extend; an edge already at its bound contributes nothing while
  the other edge continues. The action remains available while any edge can
  still extend or any internal gap remains.
- FR7: The action is disabled (and visibly indicates that no further context is
  available) once no internal gap remains and both edges have reached their
  bounds.
- FR8: The **Generate AI summary** action summarizes the full set of segments
  currently loaded in the panel — matched segments plus every loaded context
  segment — in structural order. The interpretant set sent with the request
  remains the hotspot's matched interpretants (refines master FR54; the request
  still carries one hotspot's text and its own interpretants only).
- FR9: Context is drawn only from the same source as the hotspot. Expansion
  never crosses into another source or another hotspot.
- FR10: Loaded context is scoped to the individual hotspot. Selecting a
  different hotspot presents that hotspot's own matched segments with no context
  carried over; a new query resets all expansion.
- FR11: Context segments display their verbatim text and structural locator with
  no client-side truncation, consistent with master FR46/FR52. Interpretant
  chips continue to anchor to and scroll to their matched segments after context
  is loaded; context segments are never chip targets.
- FR12: The backend exposes retrieval of a source's segments by structural
  coordinate — a contiguous ordinal range within one source — returning each
  segment's verbatim text, structural locator, ordinal, and section, executed
  through the existing stores without running a similarity query. This is
  sufficient for the client to render context and to determine chapter
  boundaries (FR4) and source ends (FR5).
- FR13: A context-load request that fails returns a distinct, client-visible
  error without altering or clearing the displayed hotspot or the current query
  result (consistent with master FR54's error stance).
