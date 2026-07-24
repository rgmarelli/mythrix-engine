import { useEffect, useMemo, useState } from 'react';
import { fetchQuery, postAgentTurn } from '../api/client';
import type { AgentCard, AgentUiSelection, Hotspot, HotspotQueryResult } from '../api/types';
import { hotspotTitle } from '../utils/hotspot';

// Mirrors `Settings.retrieval_min_score`'s default (`src/mythrix/core/config.py`)
// for display only — a `minScore` of `null` sends no `min_score` param at all,
// so the server's own default always governs unless the user overrides it.
export const DEFAULT_MIN_SCORE = 0.6;

export type ThreadItem =
  | { kind: 'user'; id: string; text: string }
  | { kind: 'ai'; id: string; text: string; cards: AgentCard[] }
  | { kind: 'reset'; id: string; label: string }
  | { kind: 'error'; id: string; text: string };

let nextItemId = 0;
export function itemId(): string {
  nextItemId += 1;
  return `item-${nextItemId}`;
}

// One independent unit of workspace state (specs/tabbed-workspace-redesign):
// a query selection, its facets/result/selected hotspot, and its own agent
// session/thread. Tabs never share or merge state with one another (FR84).
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

let nextTabId = 0;
function makeTab(): Tab {
  nextTabId += 1;
  return {
    id: `tab-${nextTabId}`,
    selectedSystem: '',
    selectedSymbol: '',
    selectedTradition: '',
    minScore: null,
    queryResult: null,
    isQuerying: false,
    queryError: null,
    selectedSourceId: null,
    selectedInterpretant: null,
    selectedRegionId: null,
    interpretantSearch: '',
    agentSessionId: crypto.randomUUID(),
    agentItems: [],
    agentSending: false,
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

/** Owns the tab array and every piece of state/derived data that used to be
 * flat on `App.tsx` (specs/tabbed-workspace-redesign) — one query selection,
 * its facets/result/selected hotspot, and its own agent session/thread,
 * fully isolated per tab (FR84). Existing presentational components
 * (`SignTraditionPicker`, `FacetRow`, `HotspotList`, `HotspotDetailPanel`)
 * need no prop changes: this hook's setters match their existing callback
 * shapes exactly, just scoped to whichever tab is active. */
export function useTabs() {
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
  // viewer always has at least one tab (FR85).
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
  const setSymbol = (value: string) => updateActiveTab({ selectedSymbol: value });
  const setTradition = (value: string) => updateActiveTab({ selectedTradition: value });
  const setMinScore = (value: number | null) => updateActiveTab({ minScore: value });
  const setSourceId = (value: string | null) => updateActiveTab({ selectedSourceId: value });
  const setInterpretant = (value: string | null) => updateActiveTab({ selectedInterpretant: value });
  const setInterpretantSearch = (value: string) => updateActiveTab({ interpretantSearch: value });
  const setRegionId = (value: string | null) => updateActiveTab({ selectedRegionId: value });

  async function runQuery() {
    const tabId = activeTabId;
    const tab = tabs.find((t) => t.id === tabId);
    if (!tab) return;

    updateTab(tabId, { isQuerying: true, queryError: null, selectedSourceId: null, selectedInterpretant: null });

    try {
      const result = await fetchQuery(tab.selectedSymbol, tab.selectedTradition, { minScore: tab.minScore ?? undefined });
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
    const filtered = activeTab.queryResult.hotspots.filter(
      (hotspot) =>
        (activeTab.selectedSourceId === null || hotspot.source.id === activeTab.selectedSourceId) &&
        (activeTab.selectedInterpretant === null ||
          hotspot.matches.some((m) => m.interpretant === activeTab.selectedInterpretant)),
    );
    return [...filtered].sort((a, b) => {
      if (a.convergenceCount !== b.convergenceCount) return b.convergenceCount - a.convergenceCount;
      return tieBreakScore(b, activeTab.selectedInterpretant) - tieBreakScore(a, activeTab.selectedInterpretant);
    });
  }, [activeTab.queryResult, activeTab.selectedSourceId, activeTab.selectedInterpretant]);

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

  // The interpretant-search filter (FR91) only narrows which options are
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

  // Captures the sending tab's id and UI-selection snapshot at send time
  // (FR89): a reply is appended to the tab it was sent from, even if the
  // user has since switched to a different tab.
  async function sendAgentMessage(message: string) {
    const trimmed = message.trim();
    const tabId = activeTabId;
    const tab = tabs.find((t) => t.id === tabId);
    if (!trimmed || !tab || tab.agentSending) return;

    const selectedHotspot = tab.queryResult?.hotspots.find((h) => h.regionId === tab.selectedRegionId) ?? null;
    const uiSelection: AgentUiSelection = {
      semioticSystem: tab.selectedSystem || null,
      sign: tab.selectedSymbol || null,
      tradition: tab.selectedTradition || null,
      sourceId: tab.selectedSourceId,
      interpretant: tab.selectedInterpretant,
      minScore: tab.minScore,
      regionId: tab.selectedRegionId,
      // Human-readable locator (e.g. "Ecclesiasticus 43:1-4") alongside the
      // structural region_id, so the agent's context summary can quote a
      // citation directly instead of only the source_id::ordinals coordinate.
      locator: selectedHotspot?.locator || null,
    };

    const userItem: ThreadItem = { kind: 'user', id: itemId(), text: trimmed };
    updateTab(tabId, (t) => ({ agentItems: [...t.agentItems, userItem], agentSending: true }));

    try {
      const result = await postAgentTurn(tab.agentSessionId, trimmed, uiSelection);
      const aiItem: ThreadItem = { kind: 'ai', id: itemId(), text: result.replyText, cards: result.cards };
      updateTab(tabId, (t) => {
        if (result.threadReset) {
          const hotspot = t.queryResult?.hotspots.find((h) => h.regionId === t.selectedRegionId) ?? null;
          const label = hotspot ? `now reading ${hotspotTitle(hotspot)}` : 'new thread';
          return { agentItems: [{ kind: 'reset', id: itemId(), label }, userItem, aiItem], agentSending: false };
        }
        return { agentItems: [...t.agentItems, aiItem], agentSending: false };
      });
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
  // already abandons its session (FR90) — not explicitly torn down server-side.
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
    setSymbol,
    setTradition,
    setMinScore,
    setSourceId,
    setInterpretant,
    setInterpretantSearch,
    setRegionId,
    runQuery,
    rankedHotspots,
    sourceFacetOptions,
    interpretantFacetOptions,
    selectedHotspot,
    selectedIndex,
    sendAgentMessage,
    clearAgentThread,
  };
}
