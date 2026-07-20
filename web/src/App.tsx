import { useEffect, useRef, useState } from 'react';
import { fetchSymbols, fetchTraditions, streamQuery } from './api/client';
import type { ConceptCandidates, ConceptPairCandidates, GraphFacts, RetrievedPassage, SymbolSummary, Tradition } from './api/types';
import { ConceptCandidatesSection } from './components/ConceptCandidatesSection';
import { GraphFactsPanel } from './components/GraphFactsPanel';
import { PairCandidatesSection } from './components/PairCandidatesSection';
import { PassageDetailPanel } from './components/PassageDetailPanel';
import { SymbolTraditionPicker } from './components/SymbolTraditionPicker';

function App() {
  const [symbols, setSymbols] = useState<SymbolSummary[]>([]);
  const [traditions, setTraditions] = useState<Tradition[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selectedSymbol, setSelectedSymbol] = useState('');
  const [selectedTradition, setSelectedTradition] = useState('');

  const [graphFacts, setGraphFacts] = useState<GraphFacts | null>(null);
  const [conceptCandidates, setConceptCandidates] = useState<ConceptCandidates[]>([]);
  const [pairCandidates, setPairCandidates] = useState<ConceptPairCandidates[]>([]);
  const [selectedPassage, setSelectedPassage] = useState<RetrievedPassage | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);

  const stopStreamRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    fetchTraditions().then(setTraditions).catch((error: Error) => setLoadError(error.message));
    fetchSymbols().then(setSymbols).catch((error: Error) => setLoadError(error.message));
    return () => stopStreamRef.current?.();
  }, []);

  function handleSubmit() {
    stopStreamRef.current?.();

    setGraphFacts(null);
    setConceptCandidates([]);
    setPairCandidates([]);
    setSelectedPassage(null);
    setStreamError(null);
    setIsStreaming(true);

    stopStreamRef.current = streamQuery(selectedSymbol, selectedTradition, {
      onGraphFacts: setGraphFacts,
      onConceptCandidates: (data) => setConceptCandidates((prev) => [...prev, data]),
      onPairCandidates: (data) => setPairCandidates((prev) => [...prev, data]),
      onDone: () => setIsStreaming(false),
      onError: (message) => {
        setStreamError(message);
        setIsStreaming(false);
      },
    });
  }

  return (
    <div className="app">
      <header>
        <h1>Mythrix — Query Viewer</h1>
        {loadError && <p className="error">{loadError}</p>}
        <SymbolTraditionPicker
          symbols={symbols}
          traditions={traditions}
          selectedSymbol={selectedSymbol}
          selectedTradition={selectedTradition}
          isStreaming={isStreaming}
          onSymbolChange={setSelectedSymbol}
          onTraditionChange={setSelectedTradition}
          onSubmit={handleSubmit}
        />
      </header>

      <main>
        <div className="results">
          {graphFacts && <GraphFactsPanel graphFacts={graphFacts} />}
          {conceptCandidates.map((candidates) => (
            <ConceptCandidatesSection
              key={candidates.concept}
              candidates={candidates}
              selectedPassage={selectedPassage}
              onSelectPassage={setSelectedPassage}
            />
          ))}
          {pairCandidates.map((pair) => (
            <PairCandidatesSection
              key={pair.concepts.join('::')}
              pair={pair}
              selectedPassage={selectedPassage}
              onSelectPassage={setSelectedPassage}
            />
          ))}
          {isStreaming && <p className="streaming-indicator">Streaming…</p>}
          {streamError && <p className="error">{streamError}</p>}
        </div>

        <PassageDetailPanel passage={selectedPassage} />
      </main>
    </div>
  );
}

export default App;
