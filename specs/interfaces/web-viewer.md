# Web Viewer

The tabbed frontend presenting [Ranking](../retrieval/ranking.md) results, backed by the [Backend API](api.md), with a docked [Conversational Agent](agent.md) panel.

## Vocabulary

- **tab**: An independent unit of web-viewer workspace state — one semiotic system/sign/tradition/min-score selection, its facet selections, its query result (if any), its selected hotspot, and its own agent chat session and thread. Tabs never share or merge state with one another.

## Functional requirements

### Query, results, and facets

- FR-WEB-01: Within each open tab (FR-WEB-06), the web viewer presents a form to select one semiotic system, one sign, and one tradition, the sign selector scoped by the chosen semiotic system, restricted to sign/tradition combinations that have a manifestation.
- FR-WEB-02: Within a tab, a query result is a single ranked list of regions ([ranking.md](../retrieval/ranking.md) FR-RK-07), together with facet data: one entry per corpus source with a count of matching regions, and one entry per interpretant with a count of regions it matched. Two independent, AND-combined, single-select facets (Sources, Interpretants) filter the displayed region list; selecting a value in one facet with the other left at "All" filters across every value of the other. Each facet's counts (including "All") are scoped to the region set satisfying the *other* facet's current selection, recomputed whenever either selection changes; a facet's own selection never scopes its own counts.
- FR-WEB-03: A region list shows each region's title, its convergence count, and which interpretants matched it; the active/selected region is visually distinguished. A detail panel shows the selected region's full verbatim segment text and complete citation, with no client-side truncation, one chip per matched interpretant with its individual match (the interpretant(s) satisfying the active facet filter visually distinguished from the rest, none hidden), navigation to the previous/next region within the current filtered, ranked list, and an action to copy the region's citation/reference string. The panel's **Add Context** action is specified in [context-expansion.md](../retrieval/context-expansion.md).
- FR-WEB-04: The query form offers an optional minimum-score input, applied to the next query submission only; left blank, no override is sent and the server's own default governs.
- FR-WEB-05: The web frontend is a separate, independently buildable application from the Python package, within the same repository; a production build of it can be served by the backend API process.

### Tabbed workspace & redesign

- FR-WEB-06: The web viewer holds one or more tabs at a time. Each tab owns, in isolation from every other tab: the selected semiotic system, sign, tradition, and min-score override (FR-WEB-01/FR-WEB-04); the current query result, if any (FR-WEB-02); the Sources/Interpretants facet selections and the interpretant-search filter text (FR-WEB-02, FR-WEB-13); and the selected hotspot (FR-WEB-03). Changing any of these in one tab never affects another tab's state.
- FR-WEB-07: A tab strip, in the top bar, lists every open tab in creation order and visually distinguishes the active tab. The user can: switch to any tab by selecting it; open a new, empty tab; and close any tab. Closing the only remaining open tab replaces it with a new, empty tab — the viewer always has at least one tab.
- FR-WEB-08: A tab's displayed label reflects its own state: the queried sign's name once that tab has a result, otherwise a placeholder indicating no query has run yet in that tab.
- FR-WEB-09: A new tab starts with no system/sign/tradition selected, no query result, and no facet selections — the same empty state the viewer has before a first query — never copying another tab's selections.
- FR-WEB-10: The docked agent chat panel ([agent.md](agent.md)) is a single, shared dock (its collapsed/expanded state is not per-tab), but its grounding context and its message thread always reflect the active tab: the context strip shows the active tab's selected hotspot (or that none is selected), and the thread shown is that tab's own thread and no other's. Switching tabs switches which tab's context and thread the dock displays; it never merges two tabs' threads.
- FR-WEB-11: Each tab has its own agent session (its own session id and its own conversation history/context, per [agent.md](agent.md) FR-AG-17's per-session context state). A message sent from one tab is answered within that tab's own thread and session even if the user switches to a different tab before the reply arrives; the reply is appended to the originating tab's thread, not whichever tab happens to be active when it arrives.
- FR-WEB-12: Closing a tab discards that tab's agent session and thread along with the rest of its state (FR-WEB-06); it is not recoverable.
- FR-WEB-13: The Interpretants facet (FR-WEB-02) offers a text filter over the facet's own option labels; it narrows which interpretant options are listed, without changing the interpretant selection itself or any facet count. This filter text is part of a tab's own state (FR-WEB-06).
- FR-WEB-14: The web viewer's visual presentation follows a single, shared design system across the whole shell, including the agent panel: a warm color palette, a serif/sans/monospace type system, and a layout of a top bar (brand + tab strip), a control panel (query form + facets), a hotspot rail, and a hotspot detail reading pane, collapsing the control panel and detail pane into slide-over drawers below a defined viewport breakpoint. No functional requirement established elsewhere in this spec changes as a result of this restyling — every existing behavior (facet AND-filtering, hotspot navigation, Add Context, copy reference, agent chat) is preserved, only its presentation changes.
- FR-WEB-15: The agent dock's visual design tokens are reconciled with the rest of the shell's tokens — it does not define its own, separate color palette.

## Non-goals

- A UI for comparing multiple interpretive traditions of the same sign against each other (consistent with the cross-tradition-comparison Non-goal in [domain-model.md](../domain/domain-model.md)).
