import { useEffect, useMemo, useState } from 'react';
import { fetchQuery, fetchSymbols, fetchTraditions } from './api/client';
import type { Fragment, FragmentQueryResult, SignSummary, Tradition } from './api/types';
import { FacetRow } from './components/FacetRow';
import { FragmentDetailPanel } from './components/FragmentDetailPanel';
import { HotspotList } from './components/HotspotList';
import { SignTraditionPicker } from './components/SignTraditionPicker';

function tieBreakScore(fragment: Fragment, activeInterpretant: string | null): number {
  if (activeInterpretant !== null) {
    const match = fragment.matches.find((m) => m.interpretant === activeInterpretant);
    if (match) return match.score;
  }
  return Math.max(0, ...fragment.matches.map((m) => m.score));
}

function hotspotHeaderText(sourceLabel: string | null, interpretantValue: string | null): string {
  if (interpretantValue !== null && sourceLabel !== null) {
    return `Fragments matching "${interpretantValue}" in ${sourceLabel} — ranked by total interpretants converging in each fragment`;
  }
  if (interpretantValue !== null) {
    return `Fragments matching "${interpretantValue}" — ranked by total interpretants converging in each fragment`;
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

  const [queryResult, setQueryResult] = useState<FragmentQueryResult | null>(null);
  const [isQuerying, setIsQuerying] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);

  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [selectedInterpretant, setSelectedInterpretant] = useState<string | null>(null);
  const [selectedFragmentId, setSelectedFragmentId] = useState<string | null>(null);

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
      const result = await fetchQuery(selectedSymbol, selectedTradition);
      setQueryResult(result);
      setSelectedFragmentId(result.fragments[0]?.chunk_id ?? null);
    } catch (error) {
      setQueryResult(null);
      setSelectedFragmentId(null);
      setQueryError(error instanceof Error ? error.message : 'Query failed.');
    } finally {
      setIsQuerying(false);
    }
  }

  const rankedFragments = useMemo(() => {
    if (!queryResult) return [];
    const filtered = queryResult.fragments.filter(
      (fragment) =>
        (selectedSourceId === null || fragment.source.id === selectedSourceId) &&
        (selectedInterpretant === null || fragment.matches.some((m) => m.interpretant === selectedInterpretant)),
    );
    return [...filtered].sort((a, b) => {
      if (a.convergence_count !== b.convergence_count) return b.convergence_count - a.convergence_count;
      return tieBreakScore(b, selectedInterpretant) - tieBreakScore(a, selectedInterpretant);
    });
  }, [queryResult, selectedSourceId, selectedInterpretant]);

  useEffect(() => {
    if (!rankedFragments.some((fragment) => fragment.chunk_id === selectedFragmentId)) {
      setSelectedFragmentId(rankedFragments[0]?.chunk_id ?? null);
    }
  }, [rankedFragments, selectedFragmentId]);

  const selectedFragment = rankedFragments.find((fragment) => fragment.chunk_id === selectedFragmentId) ?? null;
  const selectedIndex = selectedFragment ? rankedFragments.indexOf(selectedFragment) : -1;

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
          isStreaming={isQuerying}
          onSystemChange={setSelectedSystem}
          onSymbolChange={setSelectedSymbol}
          onTraditionChange={setSelectedTradition}
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
              allCount={queryResult.fragments.length}
              options={queryResult.facets.sources.map((s) => ({ id: s.id, label: s.label, count: s.count }))}
              selected={selectedSourceId}
              onSelect={setSelectedSourceId}
            />
            <FacetRow
              title="Interpretants"
              allLabel="All"
              allCount={queryResult.fragments.length}
              options={queryResult.facets.interpretants.map((i) => ({ id: i.value, label: i.value, count: i.count }))}
              selected={selectedInterpretant}
              onSelect={setSelectedInterpretant}
            />

            <div className="results-grid">
              <HotspotList
                headerText={hotspotHeaderText(selectedSourceLabel, selectedInterpretant)}
                fragments={rankedFragments}
                selectedChunkId={selectedFragmentId}
                onSelect={setSelectedFragmentId}
              />
              <FragmentDetailPanel
                key={selectedFragment?.chunk_id ?? 'empty'}
                fragment={selectedFragment}
                activeInterpretant={selectedInterpretant}
                canGoPrev={selectedIndex > 0}
                canGoNext={selectedIndex >= 0 && selectedIndex < rankedFragments.length - 1}
                onPrev={() => {
                  if (selectedIndex > 0) setSelectedFragmentId(rankedFragments[selectedIndex - 1].chunk_id);
                }}
                onNext={() => {
                  if (selectedIndex >= 0 && selectedIndex < rankedFragments.length - 1) {
                    setSelectedFragmentId(rankedFragments[selectedIndex + 1].chunk_id);
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
