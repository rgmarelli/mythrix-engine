# Tabbed Workspace Redesign — Tasks

Ordered so the state layer lands first and is independently sane (T1), then
the one component whose props actually change (T2-T3), then the new
composition components (T4-T6), then the restyled existing components
(T7-T9), then `App.tsx` rewiring (T10), then the global visual redesign
(T11-T12), then verification (T13-T14).

## State layer

- [x] **T1 — New `web/src/state/useTabs.ts`.**
  `Tab` interface, `ThreadItem` union + `itemId()` counter (moved verbatim
  from `AgentChatPanel.tsx`), and `useTabs()` returning `tabs`, `activeTabId`,
  `activeTab`, `selectTab`, `addTab`, `closeTab` (replaces-last-tab
  behavior), the active-tab-scoped field setters (`setSystem`, `setSymbol`,
  `setTradition`, `setMinScore`, `setSourceId`, `setInterpretant`,
  `setInterpretantSearch`, `setRegionId`), `runQuery()` (ported from
  `App.tsx`'s current `handleSubmit`), the three derived `useMemo`s
  (`rankedHotspots`, `sourceFacetOptions`, `interpretantFacetOptions`, the
  last filtered by `interpretantSearch`), the region-auto-reselect effect,
  and `sendAgentMessage(message)` (ported from `AgentChatPanel`'s current
  `handleSend`, capturing `tabId` at call time per plan.md's Data flow).
  Exactly per plan.md's Architecture section.

## Component changes

- [x] **T2 — `FacetRow.tsx`: optional search props.**
  Add `search?: string` and `onSearchChange?: (value: string) => void`;
  when both are present, render the mockup's `.facet-search` input (icon +
  text input) above the option list, calling `onSearchChange` on input.
  When either is omitted, render exactly as today — no change to the
  Sources row's call site.

- [x] **T3 — `AgentChatPanel.tsx`: controlled thread/session.**
  Remove the internal `sessionId`/`items` state and the network call inside
  `handleSend`. New props: `sessionId: string`, `items: ThreadItem[]`,
  `isSending: boolean`, `onSend: (message: string) => void`. The composer's
  submit handler now just calls `onSend(inputValue.trim())` and clears
  `inputValue` (guard: ignore empty/while-sending, same as today). Keep
  `inputValue` and `collapsed` as local state, unchanged otherwise. Import
  `ThreadItem` from `web/src/state/useTabs.ts` instead of defining it
  locally.

## New composition components

- [x] **T4 — New `web/src/components/TabStrip.tsx`.**
  Props: `tabs: Tab[]`, `activeTabId: string`, `signs: SignSummary[]`,
  `onSelect(id)`, `onClose(id)`, `onAdd()`. Renders one pill per tab (label
  per FR86: queried symbol's `canonical_name` from `signs` once
  `tab.queryResult` is set, else "New query"), a close control per tab, and
  an add button, matching the mockup's `.tabstrip`/`.tab`/`.tab-add`
  markup/classes.

- [x] **T5 — New `web/src/components/TopBar.tsx`.**
  Brand mark + name (ported from the mockup's `.brand` markup) plus
  `TabStrip`, matching `.topbar`. Replaces the contents of `App.tsx`'s
  current `<header>`.

- [x] **T6 — New `web/src/components/ControlPanel.tsx`.**
  Composes the existing `SignTraditionPicker` and two `FacetRow`s (Sources;
  Interpretants with `search`/`onSearchChange` wired per T2) inside one
  `<aside className="control-panel">`, matching the mockup's
  `.control-panel`/`.panel-section` structure. Pure layout composition —
  props are exactly the union of what `SignTraditionPicker` and the two
  `FacetRow`s already need; no new logic.

## Restyled existing components

- [x] **T7 — `HotspotList.tsx` / `HotspotCard.tsx`: rail visuals.**
  Update markup/class names to the mockup's `.hotspot-rail`/`.rail-header`/
  `.hotspot-card`/`.hc-top`/`.hc-badge`/`.hc-dots`/`.conv-chip` (one chip per
  match, `interpretant · score.toFixed(2)`, replacing today's comma-joined
  subtitle). No prop, callback, or sort/filter logic change.

- [x] **T8 — `HotspotDetailPanel.tsx`: reader visuals.**
  Update markup/class names to the mockup's `.reader`/`.reader-inner`/
  `.reader-toolbar`/`.breadcrumb`/`.nav-btns` (prev/next icon buttons at the
  top, in addition to the existing footer text buttons), `.reader-title-row`,
  `.chip-row`, `.segment-list`, `.reader-footer`. No prop, callback, or
  Add-Context/gap-loading logic change (`specs/hotspot-context-expansion`
  untouched).

- [x] **T9 — Mobile drawer wiring in `App.tsx`.**
  Two local booleans (`filtersOpen`, `readerOpen`), a filters-toggle button
  in `TopBar`/`App.tsx` (visible only under the mockup's breakpoint via
  CSS), a backdrop element, and a back button inside the reader — matching
  the mockup's `#filtersToggle`/`#backdrop`/`.reader-back` behavior. Opening
  a hotspot on narrow viewports opens the reader overlay; the backdrop and
  back button close it.

## `App.tsx` rewrite

- [x] **T10 — Rewrite `App.tsx` around `useTabs()`.**
  Replace the flat `useState` calls with `const tabs = useTabs()` (per T1);
  render `TopBar` (T5), `ControlPanel` (T6), `HotspotList`, restyled
  `HotspotDetailPanel` (T7-T8), and `AgentChatPanel` (T3) against
  `activeTab`'s fields/derived values and the hook's setters, wired the same
  way today's props already are (e.g. `onSystemChange={setSystem}`). Keep
  the mount-time `fetchTraditions`/`fetchSymbols` effect and `loadError`
  exactly as today (app-level, not tab-scoped). Pass `AgentChatPanel`
  `sessionId={activeTab.agentSessionId}`, `items={activeTab.agentItems}`,
  `isSending={activeTab.agentSending}`, `onSend={sendAgentMessage}`,
  `selectedHotspot={selectedHotspot}` (from the hook's derived value).

## Visual redesign

- [x] **T11 — `index.css`: design tokens, fonts, and grid shell.**
  Replace the `:root` token block with spec.md's Design tokens; add the
  Fraunces/Literata/Inter/IBM Plex Mono `@import` (as the mockup does);
  replace `.app`'s flex-column layout with the mockup's `.shell` CSS Grid
  (topbar row + control-panel/hotspot-rail/reader columns) and its
  `@media (max-width: 1000px)` responsive rules; port every class the
  restyled components (T4-T9) now render against, 1:1 from
  `specs/tabbed-workspace-redesign/mythrix-redesign.html`'s `<style>` block.

- [x] **T12 — `.agent-dock` token reconciliation (FR93).**
  Redefine the existing `--agent-*` custom properties (kept, so no other
  `.agent-dock` rule needs editing) as aliases of the new shell tokens
  (`--agent-violet: var(--violet)`, `--agent-paper: var(--paper)`, etc.)
  instead of their current separate literal colors. Update `web/index.html`'s
  `<title>` to match the mockup if it differs.

## Verification

- [x] **T13 — Lint/format/build.**
  `ruff check .` / `ruff format .` (no-op sanity check, no Python changed);
  `oxlint` and `tsc -b && vite build` for `web/` — must be clean.

- [x] **T14 — End-to-end manual check (`/run`).**
  Ran the real API (`uvicorn`, already up against the ingested `.mythrix/`
  dataset) + Vite dev server, driven live in a browser via the Claude-in-
  Chrome tools (`chromium-cli` wasn't available in this environment):
  (a) verified — opened a second tab, queried The Sun/rider-waite in the
  first and Death/marseille in the second; both kept fully independent
  facets, results, and selected hotspot; (b) verified — sent a message in
  the "Death" tab, switched to "The Sun" tab *before* the reply arrived
  (confirmed "The Sun"'s own thread/context stayed untouched, showing no
  cross-leak), then switched back to "Death" and confirmed the reply had
  landed there, correctly appended to that tab's own thread with its own
  reset divider; (c) verified — closed the active "Death" tab with two
  open, "The Sun" became active with its state untouched; (d) verified —
  closed the only remaining tab, it was replaced by one fresh empty tab;
  (f) verified — the interpretant-search filter (FR91) narrows the list
  without changing counts, Add Context gap-fills dashed context segments
  correctly, and the reader's top prev/next icon buttons navigate hotspots
  and update the agent dock's context strip client-side. (e) **not
  verified live** — `resize_window` on the Claude-in-Chrome tab did not
  change the rendered viewport in this environment (screenshots stayed at
  the original size regardless of the requested window size), so the
  `@media (max-width: 1000px)` drawer behavior could not be exercised in a
  real browser this session; it was instead verified by code review against
  `specs/tabbed-workspace-redesign/mythrix-redesign.html`'s original, working media query, ported
  unchanged. No console errors were observed during the session.
