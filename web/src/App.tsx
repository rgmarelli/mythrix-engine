import { useEffect, useMemo, useState } from 'react';
import { fetchQuery, fetchSymbols, fetchTraditions } from './api/client';
import type { Hotspot, HotspotQueryResult, SignSummary, Tradition } from './api/types';
import { FacetRow } from './components/FacetRow';
import { HotspotDetailPanel } from './components/HotspotDetailPanel';
import { HotspotList } from './components/HotspotList';
import { SignTraditionPicker } from './components/SignTraditionPicker';

function tieBreakScore(hotspot: Hotspot, activeInterpretant: string | null): number {
  if (activeInterpretant !== null) {
    const match = hotspot.matches.find((m) => m.interpretant === activeInterpretant);
    if (match) return match.score;
  }
  return Math.max(0, ...hotspot.matches.map((m) => m.score));
}

// Mirrors `Settings.retrieval_min_score`'s default (`src/mythrix/core/config.py`)
// for display only — a `minScore` of `null` sends no `min_score` param at all,
// so the server's own default always governs unless the user overrides it.
const DEFAULT_MIN_SCORE = 0.45;

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

  const [selectedSystem, setSelectedSystem] = useState('');
  const [selectedSymbol, setSelectedSymbol] = useState('');
  const [selectedTradition, setSelectedTradition] = useState('');
  const [minScore, setMinScore] = useState<number | null>(null);

  const [queryResult, setQueryResult] = useState<HotspotQueryResult | null>(null);
  const [isQuerying, setIsQuerying] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);

  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [selectedInterpretant, setSelectedInterpretant] = useState<string | null>(null);
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);

  useEffect(() => {
    fetchTraditions().then(setTraditions).catch((error: Error) => setLoadError(error.message));
    fetchSymbols().then(setSigns).catch((error: Error) => setLoadError(error.message));
  }, []);

  async function handleSubmit() {
    setQueryError(null);
    setIsQuerying(true);
    setSelectedSourceId(null);
    setSelectedInterpretant(null);

    try {
      const result = await fetchQuery(selectedSymbol, selectedTradition, { minScore: minScore ?? undefined });
      setQueryResult(result);
      setSelectedRegionId(result.hotspots[0]?.regionId ?? null);
    } catch (error) {
      setQueryResult(null);
      setSelectedRegionId(null);
      setQueryError(error instanceof Error ? error.message : 'Query failed.');
    } finally {
      setIsQuerying(false);
    }
  }

  const rankedHotspots = useMemo(() => {
    if (!queryResult) return [];
    const filtered = queryResult.hotspots.filter(
      (hotspot) =>
        (selectedSourceId === null || hotspot.source.id === selectedSourceId) &&
        (selectedInterpretant === null || hotspot.matches.some((m) => m.interpretant === selectedInterpretant)),
    );
    return [...filtered].sort((a, b) => {
      if (a.convergenceCount !== b.convergenceCount) return b.convergenceCount - a.convergenceCount;
      return tieBreakScore(b, selectedInterpretant) - tieBreakScore(a, selectedInterpretant);
    });
  }, [queryResult, selectedSourceId, selectedInterpretant]);

  useEffect(() => {
    if (!rankedHotspots.some((hotspot) => hotspot.regionId === selectedRegionId)) {
      setSelectedRegionId(rankedHotspots[0]?.regionId ?? null);
    }
  }, [rankedHotspots, selectedRegionId]);

  const selectedHotspot = rankedHotspots.find((hotspot) => hotspot.regionId === selectedRegionId) ?? null;
  const selectedIndex = selectedHotspot ? rankedHotspots.indexOf(selectedHotspot) : -1;

  const selectedSourceLabel = queryResult?.facets.sources.find((s) => s.id === selectedSourceId)?.label ?? null;

  return (
    <div className="app">
      <header>
        <h1>Mythrix — Query Viewer</h1>
        {loadError && <p className="error">{loadError}</p>}
        <SignTraditionPicker
          signs={signs}
          traditions={traditions}
          selectedSystem={selectedSystem}
          selectedSymbol={selectedSymbol}
          selectedTradition={selectedTradition}
          minScore={minScore}
          minScoreDefault={DEFAULT_MIN_SCORE}
          isStreaming={isQuerying}
          onSystemChange={setSelectedSystem}
          onSymbolChange={setSelectedSymbol}
          onTraditionChange={setSelectedTradition}
          onMinScoreChange={setMinScore}
          onSubmit={handleSubmit}
        />
      </header>

      <main>
        {queryError && <p className="error">{queryError}</p>}

        {queryResult && (
          <>
            <FacetRow
              title="Sources"
              allLabel="All sources"
              allCount={queryResult.hotspots.length}
              options={queryResult.facets.sources.map((s) => ({ id: s.id, label: s.label, count: s.count }))}
              selected={selectedSourceId}
              onSelect={setSelectedSourceId}
            />
            <FacetRow
              title="Interpretants"
              allLabel="All"
              allCount={queryResult.hotspots.length}
              options={queryResult.facets.interpretants.map((i) => ({ id: i.value, label: i.value, count: i.count }))}
              selected={selectedInterpretant}
              onSelect={setSelectedInterpretant}
            />

            <div className="results-grid">
              <HotspotList
                headerText={hotspotHeaderText(selectedSourceLabel, selectedInterpretant)}
                hotspots={rankedHotspots}
                selectedRegionId={selectedRegionId}
                onSelect={setSelectedRegionId}
              />
              <HotspotDetailPanel
                key={selectedHotspot?.regionId ?? 'empty'}
                hotspot={selectedHotspot}
                activeInterpretant={selectedInterpretant}
                canGoPrev={selectedIndex > 0}
                canGoNext={selectedIndex >= 0 && selectedIndex < rankedHotspots.length - 1}
                onPrev={() => {
                  if (selectedIndex > 0) setSelectedRegionId(rankedHotspots[selectedIndex - 1].regionId);
                }}
                onNext={() => {
                  if (selectedIndex >= 0 && selectedIndex < rankedHotspots.length - 1) {
                    setSelectedRegionId(rankedHotspots[selectedIndex + 1].regionId);
                  }
                }}
              />
            </div>
          </>
        )}
      </main>
    </div>
  );
}

export default App;
