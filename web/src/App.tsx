import { useEffect, useRef, useState } from 'react';
import { fetchSymbols, fetchTraditions, streamQuery } from './api/client';
import type { ConceptCandidates, ConceptPairCandidates, GraphFacts, RetrievedPassage, SignSummary, Tradition } from './api/types';
import { ConceptCandidatesSection } from './components/ConceptCandidatesSection';
import { GraphFactsPanel } from './components/GraphFactsPanel';
import { PairCandidatesSection } from './components/PairCandidatesSection';
import { PassageDetailPanel } from './components/PassageDetailPanel';
import { SignTraditionPicker } from './components/SignTraditionPicker';

function App() {
  const [signs, setSigns] = useState<SignSummary[]>([]);
  const [traditions, setTraditions] = useState<Tradition[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selectedSystem, setSelectedSystem] = useState('');
  const [selectedSymbol, setSelectedSymbol] = useState('');
  const [selectedTradition, setSelectedTradition] = useState('');

  const [graphFacts, setGraphFacts] = useState<GraphFacts | null>(null);
  const [conceptCandidates, setConceptCandidates] = useState<ConceptCandidates[]>([]);
  const [pairCandidates, setPairCandidates] = useState<ConceptPairCandidates[]>([]);
  const [selectedPassage, setSelectedPassage] = useState<RetrievedPassage | null>(null);
  const [selectedConcepts, setSelectedConcepts] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);

  const stopStreamRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    fetchTraditions().then(setTraditions).catch((error: Error) => setLoadError(error.message));
    fetchSymbols().then(setSigns).catch((error: Error) => setLoadError(error.message));
    return () => stopStreamRef.current?.();
  }, []);

  function selectPassage(passage: RetrievedPassage, concepts: string[]) {
    setSelectedPassage(passage);
    setSelectedConcepts(concepts);
  }

  function handleSubmit() {
    stopStreamRef.current?.();

    setGraphFacts(null);
    setConceptCandidates([]);
    setPairCandidates([]);
    setSelectedPassage(null);
    setSelectedConcepts([]);
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
        <SignTraditionPicker
          signs={signs}
          traditions={traditions}
          selectedSystem={selectedSystem}
          selectedSymbol={selectedSymbol}
          selectedTradition={selectedTradition}
          isStreaming={isStreaming}
          onSystemChange={setSelectedSystem}
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
              onSelectPassage={selectPassage}
            />
          ))}
          {pairCandidates.map((pair) => (
            <PairCandidatesSection
              key={pair.concepts.join('::')}
              pair={pair}
              selectedPassage={selectedPassage}
              onSelectPassage={selectPassage}
            />
          ))}
          {isStreaming && <p className="streaming-indicator">Streaming…</p>}
          {streamError && <p className="error">{streamError}</p>}
        </div>

        <PassageDetailPanel key={selectedPassage?.chunk_id ?? 'empty'} passage={selectedPassage} concepts={selectedConcepts} />
      </main>
    </div>
  );
}

export default App;
