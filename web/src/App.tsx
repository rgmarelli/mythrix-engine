import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { fetchSigns, fetchTraditions } from './api/client';
import type { SignSummary, Tradition } from './api/types';
import { AgentChatPanel } from './components/AgentChatPanel';
import { ControlPanel } from './components/ControlPanel';
import { HotspotDetailPanel } from './components/HotspotDetailPanel';
import { HotspotList } from './components/HotspotList';
import { TopBar } from './components/TopBar';
import { useCapabilities } from './state/useCapabilities';
import { DEFAULT_MIN_SCORE, useTabs } from './state/useTabs';

function hotspotRailHeader(count: number, search: string): ReactNode {
  const trimmed = search.trim();
  if (trimmed) {
    return (
      <>
        <b>{count}</b> match{count === 1 ? '' : 'es'} for "{trimmed}"
      </>
    );
  }
  return (
    <>
      <b>{count}</b> hotspot{count === 1 ? '' : 's'} — ranked by interpretants converging
    </>
  );
}

function App() {
  const [signs, setSigns] = useState<SignSummary[]>([]);
  const [traditions, setTraditions] = useState<Tradition[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Mobile-only slide-over drawer chrome (specs/interfaces/web-viewer.md FR-WEB-14) — UI chrome,
  // not tab data, so not tab-scoped.
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [readerOpen, setReaderOpen] = useState(false);

  useEffect(() => {
    fetchTraditions().then(setTraditions).catch((error: Error) => setLoadError(error.message));
    fetchSigns().then(setSigns).catch((error: Error) => setLoadError(error.message));
  }, []);

  const { capabilities } = useCapabilities();

  const {
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
    runQuery,
    rankedHotspots,
    sourceFacetOptions,
    interpretantFacetOptions,
    selectedHotspot,
    selectedIndex,
    augmentations,
    sendAgentMessage,
    clearAgentThread,
  } = useTabs(capabilities);

  function closeDrawers() {
    setFiltersOpen(false);
    setReaderOpen(false);
  }

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
        selectedSign={activeTab.selectedSign}
        selectedTradition={activeTab.selectedTradition}
        minScore={activeTab.minScore}
        minScoreDefault={DEFAULT_MIN_SCORE}
        isStreaming={activeTab.isQuerying}
        onSystemChange={setSystem}
        onSignChange={setSign}
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
        headerText={hotspotRailHeader(rankedHotspots.length, activeTab.hotspotSearch)}
        hasResult={activeTab.queryResult !== null}
        hotspots={rankedHotspots}
        selectedRegionId={activeTab.selectedRegionId}
        search={activeTab.hotspotSearch}
        augmentations={augmentations}
        onSearchChange={setHotspotSearch}
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
        augmentation={selectedHotspot ? (augmentations[selectedHotspot.regionId] ?? null) : null}
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
      capabilities={capabilities}
    />
    </>
  );
}

export default App;
