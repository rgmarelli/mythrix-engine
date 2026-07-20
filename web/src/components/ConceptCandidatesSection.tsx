import type { ConceptCandidates, RetrievedPassage } from '../api/types';
import { PassageCard } from './PassageCard';

interface Props {
  candidates: ConceptCandidates;
  selectedPassage: RetrievedPassage | null;
  onSelectPassage: (passage: RetrievedPassage, concepts: string[]) => void;
}

export function ConceptCandidatesSection({ candidates, selectedPassage, onSelectPassage }: Props) {
  return (
    <section className="candidates">
      <h3>Passages — "{candidates.concept}"</h3>
      <div className="passage-grid">
        {candidates.passages.map((passage) => (
          <PassageCard
            key={passage.chunk_id}
            passage={passage}
            scoreLabel={`score ${passage.score.toFixed(2)}`}
            isSelected={selectedPassage?.chunk_id === passage.chunk_id}
            onSelect={(selected) => onSelectPassage(selected, [candidates.concept])}
          />
        ))}
      </div>
    </section>
  );
}
