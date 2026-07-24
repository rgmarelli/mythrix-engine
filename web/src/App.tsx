import { useEffect, useState } from 'react';
import { fetchSymbols, fetchTraditions } from './api/client';
import type { SignSummary, Tradition } from './api/types';
import { AgentChatPanel } from './components/AgentChatPanel';
import { ControlPanel } from './components/ControlPanel';
import { HotspotDetailPanel } from './components/HotspotDetailPanel';
import { HotspotList } from './components/HotspotList';
import { TopBar } from './components/TopBar';
import { DEFAULT_MIN_SCORE, useTabs } from './state/useTabs';

function hotspotHeaderText(sourceLabel: string | null, interpretantValue: string | null): string {
  if (interpretantValue !== null && sourceLabel !== null) {
    return `Hotspots matching "${interpretantValue}" in ${sourceLabel} — ranked by total interpretants converging in each hotspot`;
  }
  if (interpretantValue !== null) {
    return `Hotspots matching "${interpretantValue}" — ranked by total interpretants converging in each hotspot`;
  }
  if (sourceLabel !== null) {
    return `Hotspots in ${sourceLabel} — ranked by distinct interpretants matched`;
  }
  return 'Hotspots — ranked by distinct interpretants matched';
}

function App() {
  const [signs, setSigns] = useState<SignSummary[]>([]);
  const [traditions, setTraditions] = useState<Tradition[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Mobile-only slide-over drawer chrome (master spec.md FR92) — UI chrome,
  // not tab data, so not tab-scoped.
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [readerOpen, setReaderOpen] = useState(false);

  useEffect(() => {
    fetchTraditions().then(setTraditions).catch((error: Error) => setLoadError(error.message));
    fetchSymbols().then(setSigns).catch((error: Error) => setLoadError(error.message));
  }, []);

  const {
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
  } = useTabs();

  function closeDrawers() {
    setFiltersOpen(false);
    setReaderOpen(false);
  }

  const selectedSourceLabel =
    activeTab.queryResult?.facets.sources.find((s) => s.id === activeTab.selectedSourceId)?.label ?? null;

  return (
    <>
    <div className="shell">
      <TopBar
        tabs={tabs}
        activeTabId={activeTabId}
        signs={signs}
        onSelectTab={selectTab}
        onCloseTab={closeTab}
        onAddTab={addTab}
        onToggleFilters={() => setFiltersOpen(true)}
      />

      <div className={filtersOpen ? 'backdrop show' : 'backdrop'} onClick={closeDrawers} />

      <ControlPanel
        signs={signs}
        traditions={traditions}
        selectedSystem={activeTab.selectedSystem}
        selectedSymbol={activeTab.selectedSymbol}
        selectedTradition={activeTab.selectedTradition}
        minScore={activeTab.minScore}
        minScoreDefault={DEFAULT_MIN_SCORE}
        isStreaming={activeTab.isQuerying}
        onSystemChange={setSystem}
        onSymbolChange={setSymbol}
        onTraditionChange={setTradition}
        onMinScoreChange={setMinScore}
        onSubmit={runQuery}
        loadError={loadError}
        queryError={activeTab.queryError}
        hasResult={activeTab.queryResult !== null}
        sourceOptions={sourceFacetOptions.options}
        sourceAllCount={sourceFacetOptions.allCount}
        selectedSourceId={activeTab.selectedSourceId}
        onSelectSourceId={setSourceId}
        interpretantOptions={interpretantFacetOptions.options}
        interpretantAllCount={interpretantFacetOptions.allCount}
        selectedInterpretant={activeTab.selectedInterpretant}
        onSelectInterpretant={setInterpretant}
        interpretantSearch={activeTab.interpretantSearch}
        onInterpretantSearchChange={setInterpretantSearch}
        open={filtersOpen}
      />

      <HotspotList
        headerText={hotspotHeaderText(selectedSourceLabel, activeTab.selectedInterpretant)}
        hasResult={activeTab.queryResult !== null}
        hotspots={rankedHotspots}
        selectedRegionId={activeTab.selectedRegionId}
        onSelect={(regionId) => {
          setRegionId(regionId);
          setReaderOpen(true);
        }}
      />

      <HotspotDetailPanel
        key={`${activeTab.id}:${selectedHotspot?.regionId ?? 'empty'}`}
        hotspot={selectedHotspot}
        hasResult={activeTab.queryResult !== null}
        activeInterpretant={activeTab.selectedInterpretant}
        canGoPrev={selectedIndex > 0}
        canGoNext={selectedIndex >= 0 && selectedIndex < rankedHotspots.length - 1}
        onPrev={() => {
          if (selectedIndex > 0) setRegionId(rankedHotspots[selectedIndex - 1].regionId);
        }}
        onNext={() => {
          if (selectedIndex >= 0 && selectedIndex < rankedHotspots.length - 1) {
            setRegionId(rankedHotspots[selectedIndex + 1].regionId);
          }
        }}
        onBack={() => setReaderOpen(false)}
        open={readerOpen}
      />
    </div>

    <AgentChatPanel
      items={activeTab.agentItems}
      isSending={activeTab.agentSending}
      onSend={sendAgentMessage}
      onClear={clearAgentThread}
      selectedHotspot={selectedHotspot}
    />
    </>
  );
}

export default App;
