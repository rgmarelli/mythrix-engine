# Tabbed Workspace Redesign — plan

## Context

`spec.md` commits to (a) a tab strip with fully isolated per-tab state, (b) a
visual redesign of the whole shell to `specs/tabbed-workspace-redesign/mythrix-redesign.html`'s tokens and
layout, and (c) the existing agent dock (`specs/in-app-agent-chat`) following
whichever tab is active, with its own thread per tab. This is a `web/`-only
change — no Python/`api/` changes, since `POST /api/agent` already keys a
conversation purely by the `session_id` the browser sends; one `session_id`
per tab is sufficient.

Today, `App.tsx` holds one flat set of `useState` calls for the entire query
(`selectedSystem` … `selectedRegionId`) and mounts one `AgentChatPanel` that
owns its own `sessionId`/thread internally. This plan (1) lifts that flat
state into an array of `Tab` objects plus an `activeTabId`, via a new hook,
`useTabs`, so every derived value (`rankedHotspots`, facet options) is
computed for "the active tab" instead of "the app"; (2) lifts the agent
thread (`sessionId`, thread items, in-flight flag) into the `Tab` object too,
since `AgentChatPanel` is now a single, persistently-mounted dock that must
show *different* data depending on which tab is active, rather than being
remounted per tab (remounting would discard, not preserve, a tab's thread —
FR89 requires the opposite); and (3) re-themes `index.css` and restructures
the layout markup to match the mockup, reusing existing presentational
components with new class names/structure rather than new logic.

## Architecture

### Tab state (`web/src/state/useTabs.ts`, new)

```ts
export interface Tab {
  id: string;
  selectedSystem: string;
  selectedSymbol: string;
  selectedTradition: string;
  minScore: number | null;
  queryResult: HotspotQueryResult | null;
  isQuerying: boolean;
  queryError: string | null;
  selectedSourceId: string | null;
  selectedInterpretant: string | null;
  selectedRegionId: string | null;
  interpretantSearch: string;
  agentSessionId: string;
  agentItems: ThreadItem[];
  agentSending: boolean;
}
```

`ThreadItem` (the discriminated union `user`/`ai`/`reset`/`error`) moves here
verbatim from its current home inline in `AgentChatPanel.tsx`, along with the
`itemId()` counter — both become exports of this module, since thread
mutation now happens here, not inside the panel component.

`useTabs()` owns one `useState<Tab[]>` plus `activeTabId`, and returns:

- `tabs`, `activeTabId`, `activeTab` (`tabs.find(t => t.id === activeTabId)`,
  never `undefined` in practice since FR85 guarantees at least one tab).
- `selectTab(id)`, `addTab()` (pushes a fresh empty `Tab`, makes it active),
  `closeTab(id)` (FR85's "always at least one tab": if closing the last tab,
  replace it with one fresh empty tab instead of leaving the array empty).
- Field setters scoped to the active tab, matching the exact prop shapes
  `SignTraditionPicker`/`FacetRow` already expect, so those two components
  need **no signature changes**: `setSystem`, `setSymbol`, `setTradition`,
  `setMinScore`, `setSourceId`, `setInterpretant`, `setInterpretantSearch`,
  `setRegionId`. Each is a small closure updating one field on whichever tab
  currently has `id === activeTabId` — never on a captured/stale tab
  reference, so a setter called right after a tab switch always lands on the
  *new* active tab.
- `runQuery()` — the existing `handleSubmit` body (`App.tsx` lines 59-76
  today), rewritten to read/write the active tab's fields instead of
  top-level state. Same error handling, same reset of source/interpretant
  filters on submit.
- `rankedHotspots`, `sourceFacetOptions`, `interpretantFacetOptions` — the
  existing three `useMemo`s (`App.tsx` lines 78-125), unchanged in logic,
  now computed from `activeTab.queryResult`/`activeTab.selectedSourceId`/
  `activeTab.selectedInterpretant` and re-run per active tab, not per app.
  `interpretantFacetOptions`'s option list is further filtered by
  `activeTab.interpretantSearch` (FR91) as one extra `.filter()` — the
  matching/counting logic itself is untouched.
- The existing region-auto-select effect (`App.tsx` lines 127-131, "if the
  selected region fell out of the filtered set, select the first one") —
  moved inside the hook, keyed so it re-runs correctly per tab.
- `sendAgentMessage(message: string)` — replaces the body of
  `AgentChatPanel.handleSend`. Captures `tabId = activeTabId` at call time
  (FR89: the reply must land in the tab that was active *when sent*, even if
  the user switches away before it resolves — mirrors the reference mockup's
  own "guard against the tab having been switched away while typing"
  comment). Appends the user `ThreadItem` to that tab's `agentItems`
  immediately, sets that tab's `agentSending = true`, calls `postAgentTurn`
  with that tab's own `agentSessionId` and its own UI-selection snapshot,
  then appends the AI/error item and clears `agentSending` on **that same
  tab** — via `setTabs(prev => prev.map(t => t.id === tabId ? {...} : t))`,
  never assuming `tabId` is still the active one.

Everything else in `App.tsx` (loading signs/traditions on mount, the
top-level `loadError`) is unrelated to tabs and stays as-is.

### Component structure

New, small, presentational components; no existing component's *props*
change except `FacetRow` (one new optional pair) and `AgentChatPanel`
(described below):

- **`TopBar.tsx`** (new) — brand mark/name + `TabStrip`. Replaces today's
  plain `<header>` contents.
- **`TabStrip.tsx`** (new) — props: `tabs`, `activeTabId`, `onSelect`,
  `onClose`, `onAdd`. Pure rendering + the three callbacks; no state of its
  own. Tab label per FR86: the queried symbol's canonical name once
  `tab.queryResult` is set, else "New query" — computed here from data
  already on the `Tab` (the symbol's display name needs `signs`, so this
  takes `signs: SignSummary[]` as a prop too, mirroring how `App.tsx`
  already holds that list).
- **`ControlPanel.tsx`** (new) — the mockup's left sidebar: composes the
  existing `SignTraditionPicker` (unchanged) and two `FacetRow`s (Sources,
  Interpretants) inside one `<aside className="control-panel">`. This is a
  pure layout composition — no new logic, just where these three existing
  pieces render relative to each other (today `SignTraditionPicker` is in
  `<header>` and both `FacetRow`s are in `<main>`; the redesign puts all
  three in one sidebar column).
- **`FacetRow.tsx`** (modified) — add two optional props, `search?: string`
  and `onSearchChange?: (value: string) => void`; when both are supplied
  (Interpretants only, per FR91) render the mockup's `.facet-search` input
  above the option list. `App.tsx`/`ControlPanel` passes them for the
  Interpretants row only; the Sources row omits them and renders exactly as
  it does today.
- **`HotspotList.tsx` / `HotspotCard.tsx`** (restyled, same props/logic) —
  new class names/structure matching the mockup's `.hotspot-rail`/
  `.hotspot-card` (a `.hc-top` header row, a `.hc-badge` convergence-count
  pill, and one `.conv-chip` per match — `interpretant · score` — replacing
  today's plain comma-joined subtitle). No prop or behavior change.
- **`HotspotDetailPanel.tsx`** (restyled, same props/logic) — restructured
  markup matching the mockup's `.reader`: breadcrumb + prev/next icon buttons
  at the top (in addition to the existing footer prev/next text buttons,
  which the mockup keeps too), interpretant chip row, `Add Context` button,
  segment list, footer. `onPrev`/`onNext`/`canGoPrev`/`canGoNext`/
  `hotspot`/`activeInterpretant` props are unchanged; `Add Context`'s
  gap/edge-loading logic (`specs/hotspot-context-expansion`) is untouched.
- **`AgentChatPanel.tsx`** (props change, described next).
- **`App.tsx`** (rewritten) — calls `useTabs()`, renders `TopBar`,
  `ControlPanel`, `HotspotList`, `HotspotDetailPanel`, `AgentChatPanel`
  against `activeTab`'s data and the hook's setters/derived values. Owns
  the two mobile-drawer booleans (`filtersOpen`, `readerOpen`) as plain
  local state — UI chrome, not tab data, so not tab-scoped (matches the
  mockup, where the drawers are `document.getElementById` toggles
  independent of its tab model).

### `AgentChatPanel` becomes a controlled dock

Today it owns `sessionId`, `items`, `inputValue`, `isSending`, `collapsed`
all locally. After this change:

- **Lifted to the active tab (via `useTabs`)**: `sessionId` → `agentSessionId`,
  `items` → `agentItems`, `isSending` → `agentSending`. Passed in as props:
  `sessionId`, `items`, `isSending`, plus `onSend(message: string)` bound to
  `sendAgentMessage`.
- **Stays local to the component**: `inputValue` (the composer's live text —
  ephemeral, cleared on send; the reference mockup doesn't persist a draft
  per tab either) and `collapsed` (FR88: one shared dock chrome state, not
  per tab).
- `contextStripText`/context-strip rendering keeps taking `selectedHotspot`
  as a prop, now always the *active* tab's selected hotspot — `App.tsx`
  passes `activeTab`'s derived `selectedHotspot` down exactly as it does
  today, just sourced from the hook instead of top-level state.
- Because the same `AgentChatPanel` instance stays mounted across tab
  switches (never remounted/keyed by tab id — remounting would reset
  `inputValue`/`collapsed` needlessly and gains nothing, since the thread
  itself now lives in `Tab`, not in the component), switching tabs simply
  re-renders it with a different `items`/`sessionId`/`isSending`/
  `selectedHotspot` — exactly FR88's "switches which tab's context and
  thread the dock displays."

### Visual redesign (`web/src/index.css`, `web/index.html`)

- Replace the existing `:root` token block and font stack with `spec.md`'s
  Design tokens (parchment/violet/gold), and add the four Google Fonts
  (Fraunces, Literata, Inter, IBM Plex Mono) via the same `@import` the
  mockup uses, added to `index.css`'s top (consistent with the mockup;
  no build-time font bundling is introduced).
- Replace the current `.app` flex-column layout with the mockup's CSS Grid
  shell (`.shell` — topbar row + 3-column row: control-panel / hotspot-rail /
  reader), including its `@media (max-width: 1000px)` responsive rules
  (control panel becomes a slide-over drawer, reader becomes a full-screen
  overlay, a filters-toggle button appears). This is a large, mostly
  mechanical port of the mockup's CSS with class names lined up to the
  restyled components above — no new visual system invented here, the
  mockup is normative.
- `.agent-dock`'s existing separate `--agent-*` custom-property block is
  replaced with the shell's own tokens (FR93): keep the same
  `--agent-*`-named custom properties (so the rest of `.agent-dock`'s rules,
  which already reference them, need no further edits) but define each as
  `var(--violet)` / `var(--paper)` / etc. instead of a separate literal
  color, per the mockup's own comment on why (a cold-neutral dock looked
  pasted-in next to a warm parchment shell).
- `web/index.html` — update `<title>` to match the mockup ("Mythrix — Query
  Viewer") if it differs; no other change (no new `<script>`/build tooling).

## Affected modules

**New `web/src/state/useTabs.ts`** — `Tab`, `ThreadItem`, `itemId()`, and the
`useTabs()` hook, as described above.

**New `web/src/components/TopBar.tsx`**, **`TabStrip.tsx`**,
**`ControlPanel.tsx`** — as described above.

**`web/src/components/FacetRow.tsx`** — add optional `search`/
`onSearchChange` props and the conditional search-input render.

**`web/src/components/HotspotList.tsx`**, **`HotspotCard.tsx`**,
**`HotspotDetailPanel.tsx`** — class-name/structure changes only; no prop or
handler signature changes.

**`web/src/components/AgentChatPanel.tsx`** — remove internal `sessionId`/
`items` state and `handleSend`'s network call; accept `sessionId`, `items`,
`isSending`, `onSend` as props instead. Keep `inputValue`, `collapsed` local.

**`web/src/App.tsx`** — rewritten to call `useTabs()` and render the new
`TopBar`/`ControlPanel` composition plus the restyled `HotspotList`/
`HotspotDetailPanel`/`AgentChatPanel`, and to own the two mobile-drawer
booleans.

**`web/src/index.css`** — token block, font import, and layout grid replaced
per Design tokens / Visual redesign above; `.agent-dock`'s token block
updated to alias the shell tokens instead of its own literals.

**`web/index.html`** — title only, if it differs from the mockup's.

No changes anywhere under `src/mythrix/` (Python) or `web/src/api/`
(`client.ts`/`types.ts`) — every existing request/response shape is reused
unchanged; `AgentUiSelection`/`AgentTurnResult` etc. are untouched.

## Data flow

**Opening a second tab.** User clicks the tab-add button. `addTab()` pushes a
fresh `Tab` (empty selections, `agentSessionId: crypto.randomUUID()`, empty
`agentItems`) and makes it active. `ControlPanel` re-renders showing empty
selects; `HotspotList`/`HotspotDetailPanel` render their existing empty
states; `AgentChatPanel` renders an empty thread with the composer disabled
(no hotspot selected yet) — all because every prop they receive now flows
from the new `activeTab`, not because any of those three components changed
behavior.

**Switching tabs mid-conversation.** Tab A has a hotspot selected and two
chat turns; the user switches to Tab B (also mid-query, different symbol).
`selectTab('B')` only changes `activeTabId` — no tab's data is touched.
`AgentChatPanel` re-renders with Tab B's `items`/`sessionId`/`selectedHotspot`
in place of Tab A's; Tab A's thread is not lost, just not shown. Switching
back to Tab A restores it exactly, pixel-for-pixel (same guarantee the
existing collapse/re-open behavior already gives within one tab).

**Sending a message, then switching away before the reply lands.** User
types in Tab A's context, hits send; `sendAgentMessage` captures
`tabId = 'A'`, appends the user bubble to Tab A, sets Tab A's
`agentSending = true`. User immediately switches to Tab B — `AgentChatPanel`
now shows Tab B's (unaffected) thread and `isSending` state. The
`postAgentTurn` promise for Tab A resolves later; the `.map(t => t.id ===
'A' ? ... : t)` update appends the AI reply to Tab A specifically and clears
Tab A's `agentSending`, regardless of which tab is active at that moment. If
the user is back on Tab A when it resolves, they see the reply appear
normally; if not, it's simply waiting there next time they switch to Tab A.

## Verification

**No new frontend test infra** (matches `specs/in-app-agent-chat`'s existing
choice — this codebase has no frontend test suite yet). Verification is
lint/build plus manual, in-browser exercise via `/run`:

- `ruff check .` / `ruff format .` are unaffected (no Python changes) but run
  anyway as a no-op sanity check; `oxlint` and `tsc -b && vite build` (or
  `vite` dev) for the frontend must be clean.
- Manual pass against the real API + Vite dev servers: (a) open a second tab,
  run a different query in each, confirm both keep independent facets/
  results/selected hotspot; (b) send a chat message in Tab A, switch to Tab B
  and send a different message there, switch back to Tab A and confirm its
  own thread and reply are intact and Tab B's reply didn't leak in; (c) close
  the active tab with two tabs open — confirm the other becomes active and
  its state is untouched; (d) close the only open tab — confirm it's
  replaced by one fresh empty tab, not zero tabs; (e) resize below the
  mockup's 1000px breakpoint — confirm the control panel and reader behave
  as slide-over drawers, matching the mockup; (f) spot-check that every
  pre-existing behavior (facet AND-filtering and counts, hotspot prev/next,
  Add Context's gap/edge-loading, copy ref, agent dock collapse/expand)
  still works unchanged within a single tab.
