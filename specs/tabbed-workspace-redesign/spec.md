# Tabbed Workspace Redesign — spec

## Purpose

A visual redesign of the web viewer, restructured around **tabs**: the user
can hold several independent queries open at once — each with its own
semiotic system/symbol/tradition selection, facets, results, and selected
hotspot — and switch between them without losing any tab's state. The
docked agent chat panel (`specs/in-app-agent-chat`) always grounds itself in,
and keeps a separate conversation thread per, the currently active tab.

## Relationship to existing architecture

- This is a **client-only** feature. No backend endpoint, request/response
  contract, or agent tool changes. `POST /api/agent` already scopes a
  conversation by a client-generated `session_id` (`specs/in-app-agent-chat`);
  giving each tab its own `session_id` is sufficient for independent agent
  threads with zero backend changes.
- Supersedes one line of `specs/in-app-agent-chat/spec.md`'s Non-goals:
  *"Reconciling the panel's design tokens with the rest of the app's existing
  token set."* This redesign reconciles them — the agent dock adopts the same
  palette as the rest of the shell (see Design tokens).
- Stays standalone (`spec.md`/`plan.md`/`tasks.md`) through implementation and
  is folded into master `specs/spec.md` on completion, same pattern as prior
  features. Folding in will need to touch master's FR50/FR51/FR52 (currently
  written in terms of a single, implicit query) — not done now.
- Reference mockup: `specs/tabbed-workspace-redesign/mythrix-redesign.html` (this handoff) — a static,
  non-wired HTML/CSS/JS mock demonstrating the target layout, tab behavior,
  and design tokens. It is not the implementation; its data arrays and
  `setTimeout`-based fake submit are stand-ins for the app's real API calls
  (`fetchQuery`, `fetchSymbols`, `fetchTraditions`, `postAgentTurn`).

## Vocabulary

Reuses master `spec.md` and `specs/in-app-agent-chat/spec.md`'s existing terms
(`hotspot`/`region`, `agent`, `session`, `thread`) without redefinition. One
new term:

- **tab**: An independent unit of workspace state: one semiotic
  system/symbol/tradition/min-score selection, its facet selections, its
  query result (or none yet), its selected hotspot, and its own agent session
  and thread. Tabs never share or merge state with one another.

## Scope

- **In scope**: the tab strip and per-tab state isolation; the visual
  redesign of the existing layout (top bar, control panel, hotspot list,
  hotspot detail) to the reference mockup's design tokens and structure,
  including its responsive/mobile behavior; the agent dock adopting the same
  tokens and following the active tab (context + thread).
- **Out of scope**: any new backend capability, any new agent tool, renaming
  a tab by hand, reordering tabs by drag, persisting tabs across a page
  reload, and anything the mockup shows the agent doing to change a filter or
  navigate hotspots on its own — that remains `in-app-agent-chat`'s deferred
  v1, unaffected by this spec.

## Functional requirements

- FR84: The web viewer holds one or more tabs at a time. Each tab owns, in
  isolation from every other tab: the selected semiotic system, symbol,
  tradition, and min-score override (master FR50/FR53); the current query
  result, if any (FR51); the Sources/Interpretants facet selections and the
  interpretant-search filter text (FR51, FR89); and the selected hotspot
  (FR52). Changing any of these in one tab never affects another tab's state.
- FR85: A tab strip, in the top bar, lists every open tab in creation order
  and visually distinguishes the active tab. The user can: switch to any tab
  by selecting it; open a new, empty tab; and close any tab. Closing the only
  remaining open tab replaces it with a new, empty tab — the viewer always
  has at least one tab.
- FR86: A tab's displayed label reflects its own state: the queried symbol's
  name once that tab has a result, otherwise a placeholder indicating no
  query has run yet in that tab.
- FR87: A new tab starts with no system/symbol/tradition selected, no query
  result, and no facet selections — the same empty state the viewer has
  today before a first query — never copying another tab's selections.
- FR88: The docked agent chat panel (`specs/in-app-agent-chat`) is a single,
  shared dock (its collapsed/expanded state is not per-tab), but its
  grounding context and its message thread always reflect the **active**
  tab: the context strip shows the active tab's selected hotspot (or that
  none is selected), and the thread shown is that tab's own thread and no
  other's. Switching tabs switches which tab's context and thread the dock
  displays; it never merges two tabs' threads.
- FR89: Each tab has its own agent session (its own `session_id` and its own
  conversation history/context, per `specs/in-app-agent-chat`'s existing
  per-session state). A message sent from one tab is answered within that
  tab's own thread and session even if the user switches to a different tab
  before the reply arrives; the reply is appended to the originating tab's
  thread, not whichever tab happens to be active when it arrives.
- FR90: Closing a tab discards that tab's agent session and thread along
  with the rest of its state (FR84); it is not recoverable.
- FR91: The Interpretants facet (master FR51) offers a text filter over the
  facet's own option labels; it narrows which interpretant options are
  listed, without changing the interpretant selection itself or any facet
  count. This filter text is part of a tab's own state (FR84).
- FR92: The web viewer's visual presentation (layout, color palette,
  typography, iconography) follows the redesign in `specs/tabbed-workspace-redesign/mythrix-redesign.html`:
  a top bar (brand + tab strip), a control panel (query form + facets), a
  hotspot list, and a hotspot detail reading pane, plus the existing
  responsive behavior collapsing the control panel and detail pane into
  slide-over drawers below the mockup's breakpoint. No functional requirement
  established elsewhere in master `spec.md` or `specs/in-app-agent-chat/spec.md`
  changes as a result of this restyling — every existing behavior (facet
  AND-filtering, hotspot navigation, Add Context, copy ref, agent chat) is
  preserved, only its presentation changes.
- FR93: The agent dock's visual design tokens are reconciled with the rest of
  the shell's tokens (Design tokens, below) — it no longer defines its own,
  separate color palette.

## Design tokens

Reuses the reference mockup's palette and type system for the whole shell,
including the agent dock:

```
--paper       #F6F1E5   page background
--panel       #FFFCF5   card/panel surface
--panel-2     #FBF6EA   recessed surface (inputs, inner cards)
--ink         #2C2418   primary text
--ink-h       #1A140C   heading text
--muted       #8A7F68   tertiary / labels
--line        #E2D8BF   borders
--line-soft   #ECE3CC   inner dividers
--violet      #33518F   primary accent
--violet-deep #25396B   hover states
--violet-wash rgba(51,81,143,.09)
--gold        #8F6417   citation / secondary accent
--rubric      #A3341F   destructive (tab close hover)
```

Type: **Fraunces** (headings, hotspot/citation titles), **Literata** (source
text), **Inter** (UI/body), **IBM Plex Mono** (scores, locators, tab-strip
labels — anything that reads as data).

## Non-goals

- Any new backend endpoint, agent tool, or change to the `POST /api/agent`
  request/response contract.
- Persisting tabs (or their agent sessions) across a page reload or backend
  restart — matches the existing agent session's non-goal
  (`specs/in-app-agent-chat`).
- Manually renaming, reordering (drag), duplicating, or pinning a tab.
- A maximum tab count, or any resource-management behavior beyond what
  already exists per-session today (each tab is exactly as expensive as the
  single implicit "tab" the viewer already has).
- Any agent-driven UI mutation (changing a facet, navigating a hotspot, or
  opening/closing a tab from chat) — still `in-app-agent-chat`'s deferred v1.
- Sharing or copying one tab's selection into another tab.
