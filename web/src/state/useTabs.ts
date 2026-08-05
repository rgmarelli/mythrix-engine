// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useMemo, useState } from 'react';
import { fetchQuery, streamAgentTurn } from '../api/client';
import { executeInstruction } from '../api/instructions';
import type {
  AgentCapabilities,
  AgentContext,
  AgentInstruction,
  Augmentation,
  ExtendedRegion,
  ExtendedRegionRef,
  Hotspot,
  HotspotQueryResult,
} from '../api/types';
import { hotspotTitle } from '../utils/hotspot';

// An instruction that carries a result rather than requesting one
// (augmentation.md FR-AU-26). Declared with no binding, so `executeInstruction`
// returns null for it and the handling lives here, by type — the same shape
// `confirm_query` already has, and no new `ResultKind` (FR-CAP-11).
const AUGMENT_REGION = 'augment_region';

function augmentationOf(instruction: AgentInstruction): { regionId: string; augmentation: Augmentation } | null {
  if (instruction.type !== AUGMENT_REGION) return null;
  const regionId = String(instruction.payload.region_id ?? '');
  const text = String(instruction.payload.augmentation ?? '');
  if (!regionId || !text) return null;
  return { regionId, augmentation: { label: String(instruction.payload.label ?? ''), text } };
}

// Mirrors `Settings.retrieval_min_score`'s default (`src/mythrix/core/config.py`)
// for display only — a `minScore` of `null` sends no `min_score` param at all,
// so the server's own default always governs unless the user overrides it.
export const DEFAULT_MIN_SCORE = 0.6;

export type ThreadItem =
  | { kind: 'user'; id: string; text: string }
  // `regionMarkers` maps a region marker (e.g. "[R1]") this item's text
  // carries to the region it names, scoped to this item alone
  // (specs/interfaces/web-viewer.md FR-WEB-28).
  | { kind: 'ai'; id: string; text: string; instructions: AgentInstruction[]; regionMarkers: Record<string, string> }
  | { kind: 'reset'; id: string; label: string }
  | { kind: 'error'; id: string; text: string };

let nextItemId = 0;
export function itemId(): string {
  nextItemId += 1;
  return `item-${nextItemId}`;
}

// One independent unit of workspace state (specs/interfaces/web-viewer.md FR-WEB-06): a query
// selection, its facets/result/selected hotspot, and its own agent
// session/thread. Tabs never share or merge state with one another.
export interface Tab {
  id: string;
  selectedSystem: string;
  selectedSign: string;
  selectedTradition: string;
  minScore: number | null;
  queryResult: HotspotQueryResult | null;
  isQuerying: boolean;
  queryError: string | null;
  selectedSourceId: string | null;
  selectedInterpretant: string | null;
  selectedRegionId: string | null;
  interpretantSearch: string;
  hotspotSearch: string;
  agentSessionId: string;
  agentItems: ThreadItem[];
  agentSending: boolean;
  // Generated readings, keyed by the region each names (FR-AU-26). Scoped to
  // this tab and discarded whenever `queryResult` is replaced (FR-AU-29): an
  // augmentation describes one focus over one result set, so showing it beside
  // a different one would misattribute it.
  augmentations: Record<string, Augmentation>;
  // Widened contexts, keyed by the hotspot each was computed for
  // (specs/tmp/hotspot-context-expansion-agent) — one entry per hotspot the
  // user has widened this tab's context for, so extending hotspot B does not
  // discard hotspot A's already-widened context (per user decision: option 1,
  // keep + surface it + a "Clear Context" affordance, not silently reset it).
  // Mirrors `augmentations` above exactly: a map keyed by region, scoped to
  // this tab, reset whenever `queryResult` is replaced.
  extendedRegions: Record<string, ExtendedRegion>;
}

let nextTabId = 0;
function makeTab(): Tab {
  nextTabId += 1;
  return {
    id: `tab-${nextTabId}`,
    selectedSystem: '',
    selectedSign: '',
    selectedTradition: '',
    minScore: null,
    queryResult: null,
    isQuerying: false,
    queryError: null,
    selectedSourceId: null,
    selectedInterpretant: null,
    selectedRegionId: null,
    interpretantSearch: '',
    hotspotSearch: '',
    agentSessionId: crypto.randomUUID(),
    agentItems: [],
    agentSending: false,
    augmentations: {},
    extendedRegions: {},
  };
}

function tieBreakScore(hotspot: Hotspot, activeInterpretant: string | null): number {
  if (activeInterpretant !== null) {
    const match = hotspot.matches.find((m) => m.interpretant === activeInterpretant);
    if (match) return match.score;
  }
  return Math.max(0, ...hotspot.matches.map((m) => m.score));
}

type TabPatch = Partial<Tab> | ((tab: Tab) => Partial<Tab>);

/** Owns the tab array and every piece of per-tab state/derived data
 * (specs/interfaces/web-viewer.md FR-WEB-06) — one query selection, its facets/result/selected
 * hotspot, and its own agent session/thread, fully isolated per tab
 * (FR-WEB-06). Existing presentational components
 * (`SignTraditionPicker`, `FacetRow`, `HotspotList`, `HotspotDetailPanel`)
 * need no prop changes: this hook's setters match their existing callback
 * shapes exactly, just scoped to whichever tab is active. */
export function useTabs(capabilities: AgentCapabilities | null = null) {
  const [tabs, setTabs] = useState<Tab[]>(() => [makeTab()]);
  const [activeTabId, setActiveTabId] = useState<string>(() => tabs[0].id);

  const activeTab = tabs.find((t) => t.id === activeTabId) ?? tabs[0];

  function updateTab(id: string, patch: TabPatch) {
    setTabs((prev) => prev.map((t) => (t.id === id ? { ...t, ...(typeof patch === 'function' ? patch(t) : patch) } : t)));
  }

  function updateActiveTab(patch: TabPatch) {
    updateTab(activeTabId, patch);
  }

  function selectTab(id: string) {
    setActiveTabId(id);
  }

  function addTab() {
    const tab = makeTab();
    setTabs((prev) => [...prev, tab]);
    setActiveTabId(tab.id);
  }

  // Closing the only remaining tab replaces it with a fresh empty one — the
  // viewer always has at least one tab (FR-WEB-07).
  function closeTab(id: string) {
    setTabs((prev) => {
      if (prev.length === 1) {
        const fresh = makeTab();
        setActiveTabId(fresh.id);
        return [fresh];
      }
      const idx = prev.findIndex((t) => t.id === id);
      const next = prev.filter((t) => t.id !== id);
      if (id === activeTabId) {
        setActiveTabId(next[Math.max(0, idx - 1)].id);
      }
      return next;
    });
  }

  const setSystem = (value: string) => updateActiveTab({ selectedSystem: value });
  const setSign = (value: string) => updateActiveTab({ selectedSign: value });
  const setTradition = (value: string) => updateActiveTab({ selectedTradition: value });
  const setMinScore = (value: number | null) => updateActiveTab({ minScore: value });
  const setSourceId = (value: string | null) => updateActiveTab({ selectedSourceId: value });
  const setInterpretant = (value: string | null) => updateActiveTab({ selectedInterpretant: value });
  const setInterpretantSearch = (value: string) => updateActiveTab({ interpretantSearch: value });
  const setHotspotSearch = (value: string) => updateActiveTab({ hotspotSearch: value });
  const setRegionId = (value: string | null) => updateActiveTab({ selectedRegionId: value });

  // Records or clears the widened context for one specific hotspot
  // (specs/tmp/hotspot-context-expansion-agent) — extending or clearing
  // hotspot B never touches hotspot A's own entry.
  function setExtendedRegion(regionId: string, region: ExtendedRegionRef) {
    updateActiveTab((t) => {
      if (region === null) {
        if (!(regionId in t.extendedRegions)) return {};
        const { [regionId]: _removed, ...rest } = t.extendedRegions;
        return { extendedRegions: rest };
      }
      return { extendedRegions: { ...t.extendedRegions, [regionId]: region } };
    });
  }

  async function runQuery() {
    const tabId = activeTabId;
    const tab = tabs.find((t) => t.id === tabId);
    if (!tab) return;

    updateTab(tabId, {
      isQuerying: true,
      queryError: null,
      selectedSourceId: null,
      selectedInterpretant: null,
      augmentations: {},
      extendedRegions: {},
    });

    try {
      const result = await fetchQuery(tab.selectedSign, tab.selectedTradition, { minScore: tab.minScore ?? undefined });
      updateTab(tabId, { queryResult: result, selectedRegionId: result.hotspots[0]?.regionId ?? null, isQuerying: false });
    } catch (error) {
      updateTab(tabId, {
        queryResult: null,
        selectedRegionId: null,
        queryError: error instanceof Error ? error.message : 'Query failed.',
        isQuerying: false,
      });
    }
  }

  const rankedHotspots = useMemo(() => {
    if (!activeTab.queryResult) return [];
    const search = activeTab.hotspotSearch.trim().toLowerCase();
    const filtered = activeTab.queryResult.hotspots.filter(
      (hotspot) =>
        (activeTab.selectedSourceId === null || hotspot.source.id === activeTab.selectedSourceId) &&
        (activeTab.selectedInterpretant === null ||
          hotspot.matches.some((m) => m.interpretant === activeTab.selectedInterpretant)) &&
        (search === '' ||
          hotspotTitle(hotspot).toLowerCase().includes(search) ||
          (hotspot.source.citation_label || hotspot.source.title).toLowerCase().includes(search) ||
          hotspot.matches.some((m) => m.interpretant.toLowerCase().includes(search))),
    );
    return [...filtered].sort((a, b) => {
      if (a.convergenceCount !== b.convergenceCount) return b.convergenceCount - a.convergenceCount;
      return tieBreakScore(b, activeTab.selectedInterpretant) - tieBreakScore(a, activeTab.selectedInterpretant);
    });
  }, [activeTab.queryResult, activeTab.selectedSourceId, activeTab.selectedInterpretant, activeTab.hotspotSearch]);

  // Selects a region named by a chat marker
  // (specs/interfaces/web-viewer.md FR-WEB-31). Only clears the
  // source/interpretant/search filters when the region is excluded from the
  // *current* display by one of them — a region already on the list is
  // selected exactly as `setRegionId` would, leaving the user's filters
  // alone.
  const navigateToRegion = (regionId: string) => {
    if (rankedHotspots.some((hotspot) => hotspot.regionId === regionId)) {
      updateActiveTab({ selectedRegionId: regionId });
      return;
    }
    updateActiveTab({ selectedSourceId: null, selectedInterpretant: null, hotspotSearch: '', selectedRegionId: regionId });
  };

  // Each facet row's counts are scoped to the *other* facet's current selection
  // (never its own), so selecting a Source narrows the Interpretants counts and
  // vice versa — mirrors `rankedHotspots`' predicate, one clause at a time.
  const sourceFacetOptions = useMemo(() => {
    if (!activeTab.queryResult) return { options: [], allCount: 0 };
    const scoped = activeTab.queryResult.hotspots.filter(
      (hotspot) =>
        activeTab.selectedInterpretant === null ||
        hotspot.matches.some((m) => m.interpretant === activeTab.selectedInterpretant),
    );
    const byId = new Map<string, { id: string; label: string; count: number }>();
    for (const hotspot of scoped) {
      const existing = byId.get(hotspot.source.id);
      if (existing) {
        existing.count += 1;
      } else {
        byId.set(hotspot.source.id, { id: hotspot.source.id, label: hotspot.source.title, count: 1 });
      }
    }
    return { options: [...byId.values()], allCount: scoped.length };
  }, [activeTab.queryResult, activeTab.selectedInterpretant]);

  // The interpretant-search filter (FR-WEB-13) only narrows which options are
  // listed; it never changes a count or the underlying selection.
  const interpretantFacetOptions = useMemo(() => {
    if (!activeTab.queryResult) return { options: [], allCount: 0 };
    const scoped = activeTab.queryResult.hotspots.filter(
      (hotspot) => activeTab.selectedSourceId === null || hotspot.source.id === activeTab.selectedSourceId,
    );
    const counts = new Map<string, number>();
    for (const hotspot of scoped) {
      for (const match of hotspot.matches) {
        counts.set(match.interpretant, (counts.get(match.interpretant) ?? 0) + 1);
      }
    }
    const search = activeTab.interpretantSearch.trim().toLowerCase();
    const options = [...counts.entries()]
      .filter(([value]) => value.toLowerCase().includes(search))
      .map(([value, count]) => ({ id: value, label: value, count }));
    return { options, allCount: scoped.length };
  }, [activeTab.queryResult, activeTab.selectedSourceId, activeTab.interpretantSearch]);

  useEffect(() => {
    if (!rankedHotspots.some((hotspot) => hotspot.regionId === activeTab.selectedRegionId)) {
      updateTab(activeTab.id, { selectedRegionId: rankedHotspots[0]?.regionId ?? null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rankedHotspots, activeTab.selectedRegionId, activeTab.id]);

  const selectedHotspot = rankedHotspots.find((hotspot) => hotspot.regionId === activeTab.selectedRegionId) ?? null;
  const selectedIndex = selectedHotspot ? rankedHotspots.indexOf(selectedHotspot) : -1;

  // The active hotspot's own widened context, if any — looked up by its own
  // regionId (specs/tmp/hotspot-context-expansion-agent), the same lookup
  // pattern `augmentations`/`selectedHotspot` already use. Independent of
  // whichever *other* hotspot's context was most recently widened.
  const activeExtendedRegion: ExtendedRegionRef = activeTab.selectedRegionId
    ? (activeTab.extendedRegions[activeTab.selectedRegionId] ?? null)
    : null;

  // Runs a turn's instructions against the tab the turn was sent from
  // (specs/interfaces/web-viewer.md FR-WEB-19), which is why `tabId` is passed
  // in rather than read from `activeTabId` — the user may have switched tabs
  // while the turn was in flight.
  async function runInstructions(instructions: AgentInstruction[], tabId: string) {
    for (const instruction of instructions) {
      const augmented = augmentationOf(instruction);
      if (augmented) {
        updateTab(tabId, (t) => ({
          augmentations: { ...t.augmentations, [augmented.regionId]: augmented.augmentation },
        }));
        continue;
      }

      // A bound instruction issues a request, so the rail shows the same
      // pending state a form submission does.
      if (capabilities?.bindings[instruction.type]) updateTab(tabId, { isQuerying: true });

      const outcome = await executeInstruction(instruction, capabilities);
      if (outcome === null) continue;

      if (outcome.kind === 'unexecutable') {
        const errorItem: ThreadItem = { kind: 'error', id: itemId(), text: outcome.reason };
        updateTab(tabId, (t) => ({ agentItems: [...t.agentItems, errorItem], isQuerying: false }));
        continue;
      }

      // A result the form did not produce must not leave the form describing
      // it — the query selections are emptied alongside the facet reset
      // (FR-WEB-20).
      updateTab(tabId, {
        queryResult: outcome.result,
        selectedRegionId: outcome.result.hotspots[0]?.regionId ?? null,
        queryError: null,
        isQuerying: false,
        selectedSourceId: null,
        selectedInterpretant: null,
        selectedSystem: '',
        selectedSign: '',
        selectedTradition: '',
        minScore: null,
        augmentations: {},
        extendedRegions: {},
      });
    }
  }

  // Captures the sending tab's id and UI-selection snapshot at send time
  // (FR-WEB-11): a reply is appended to the tab it was sent from, even if the
  // user has since switched to a different tab.
  async function sendAgentMessage(message: string) {
    const trimmed = message.trim();
    const tabId = activeTabId;
    const tab = tabs.find((t) => t.id === tabId);
    if (!trimmed || !tab || tab.agentSending) return;

    const selectedHotspot = tab.queryResult?.hotspots.find((h) => h.regionId === tab.selectedRegionId) ?? null;
    const uiSelection: AgentContext = {
      semioticSystem: tab.selectedSystem || null,
      sign: tab.selectedSign || null,
      tradition: tab.selectedTradition || null,
      interpretant: tab.selectedInterpretant,
      minScore: tab.minScore,
      regionId: tab.selectedRegionId,
      // Human-readable locator (e.g. "Ecclesiasticus 43:1-4") alongside the
      // structural region_id, so the agent's context summary can quote a
      // citation directly instead of only the source_id::ordinals coordinate.
      locator: selectedHotspot?.locator || null,
      // The widened context Add Context has grown, if any (only meaningful
      // when it still belongs to this tab's currently selected hotspot —
      // see `activeExtendedRegion`'s derivation above).
      extendedRegionId: activeExtendedRegion?.regionId ?? null,
      extendedLocator: activeExtendedRegion?.locator ?? null,
    };

    const userItem: ThreadItem = { kind: 'user', id: itemId(), text: trimmed };
    updateTab(tabId, (t) => ({ agentItems: [...t.agentItems, userItem], agentSending: true }));

    try {
      // The regions this tab is displaying, in display order (FR-AU-12) — the
      // facets, the search box and the convergence sort are already applied,
      // so the backend reproduces none of that filtering.
      const visibleRegions = rankedHotspots.map((hotspot) => hotspot.regionId);

      // Accumulates this run's marker -> region map for the consolidation
      // item below; `lastMessageItemId` lets the paired instruction event
      // patch the region's own progress item with its one marker
      // (specs/interfaces/web-viewer.md FR-WEB-28, FR-AU-23's
      // message-then-instruction pairing per region).
      const regionMarkers: Record<string, string> = {};
      let lastMessageItemId: string | null = null;

      const result = await streamAgentTurn(tab.agentSessionId, trimmed, uiSelection, visibleRegions, (event) => {
        // Progress, delivered as it happens (FR-AU-23). Applied straight away
        // rather than collected, so a long run is visible while it runs.
        if (event.event === 'message') {
          const id = itemId();
          lastMessageItemId = id;
          const item: ThreadItem = { kind: 'ai', id, text: event.text, instructions: [], regionMarkers: {} };
          updateTab(tabId, (t) => ({ agentItems: [...t.agentItems, item] }));
          return;
        }
        const augmented = augmentationOf(event.instruction);
        if (augmented) {
          regionMarkers[augmented.augmentation.label] = augmented.regionId;
          updateTab(tabId, (t) => ({
            augmentations: { ...t.augmentations, [augmented.regionId]: augmented.augmentation },
            agentItems: t.agentItems.map((item) =>
              item.id === lastMessageItemId && item.kind === 'ai'
                ? { ...item, regionMarkers: { ...item.regionMarkers, [augmented.augmentation.label]: augmented.regionId } }
                : item,
            ),
          }));
        }
      });
      const aiItem: ThreadItem = {
        kind: 'ai',
        id: itemId(),
        text: result.replyText,
        instructions: result.instructions,
        regionMarkers,
      };
      updateTab(tabId, (t) => {
        if (result.threadReset) {
          // A thread reset (FR-AG-16) fires on ordinary hotspot navigation —
          // it is a conversational-history concept, unrelated to which
          // hotspots have a remembered widened context. Clearing
          // `extendedRegions` here would discard *every* hotspot's memory
          // just for chatting after switching hotspots; only an explicit
          // "Clear Context" (per hotspot) or a new query (all hotspots
          // replaced) should do that.
          const hotspot = t.queryResult?.hotspots.find((h) => h.regionId === t.selectedRegionId) ?? null;
          const label = hotspot ? `now reading ${hotspotTitle(hotspot)}` : 'new thread';
          return {
            agentItems: [{ kind: 'reset', id: itemId(), label }, userItem, aiItem],
            agentSending: false,
          };
        }
        return { agentItems: [...t.agentItems, aiItem], agentSending: false };
      });
      await runInstructions(result.instructions, tabId);
    } catch (error) {
      const errorItem: ThreadItem = {
        kind: 'error',
        id: itemId(),
        text: error instanceof Error ? error.message : 'Something went wrong reaching the agent.',
      };
      updateTab(tabId, (t) => ({ agentItems: [...t.agentItems, errorItem], agentSending: false }));
    }
  }

  // The `/clear` composer command: wipes the active tab's visible thread and
  // starts a brand-new agent session (a fresh `session_id`), so the backend's
  // in-memory `SessionStore` (agent/sessions.py) treats the next turn as a
  // session it has never seen — no stale history or `agent_notes` carries
  // over. The old session is simply abandoned, the same way closing a tab
  // already abandons its session (FR-WEB-12) — not explicitly torn down server-side.
  function clearAgentThread() {
    updateTab(activeTabId, () => ({ agentItems: [], agentSessionId: crypto.randomUUID() }));
  }

  return {
    tabs,
    activeTabId,
    activeTab,
    selectTab,
    addTab,
    closeTab,
    setSystem,
    setSign,
    setTradition,
    setMinScore,
    setSourceId,
    setInterpretant,
    setInterpretantSearch,
    setHotspotSearch,
    setRegionId,
    setExtendedRegion,
    navigateToRegion,
    runQuery,
    rankedHotspots,
    sourceFacetOptions,
    interpretantFacetOptions,
    selectedHotspot,
    selectedIndex,
    activeExtendedRegion,
    augmentations: activeTab.augmentations,
    sendAgentMessage,
    clearAgentThread,
  };
}
