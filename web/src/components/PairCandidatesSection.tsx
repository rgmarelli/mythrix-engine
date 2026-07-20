import type { ConceptPairCandidates, MergedCandidate, RetrievedPassage } from '../api/types';
import { PassageCard } from './PassageCard';

interface Props {
  pair: ConceptPairCandidates;
  selectedPassage: RetrievedPassage | null;
  onSelectPassage: (passage: RetrievedPassage, concepts: string[]) => void;
}

/** FR6: each candidate's combined score alongside its per-concept component
 * scores, distinguishing an exact-value match (no meaningful score of its
 * own, shown by name alone — mirrors `cli/formatting.py::_render_match_component`)
 * from a semantic-similarity match (name and score). */
function scoreLabel(candidate: MergedCandidate): string {
  const components = candidate.matches
    .map((match) => (match.exact_value ? match.concept : `${match.concept} ${match.score.toFixed(2)}`))
    .join(' · ');
  return `combined ${candidate.combined_score.toFixed(2)} (${components})`;
}

export function PairCandidatesSection({ pair, selectedPassage, onSelectPassage }: Props) {
  return (
    <section className="candidates">
      <h3>Convergence — [{pair.concepts.join(', ')}]</h3>
      <div className="passage-grid">
        {pair.candidates.map((candidate) => (
          <PassageCard
            key={candidate.passage.chunk_id}
            passage={candidate.passage}
            scoreLabel={scoreLabel(candidate)}
            isSelected={selectedPassage?.chunk_id === candidate.passage.chunk_id}
            onSelect={(selected) => onSelectPassage(selected, [...pair.concepts])}
          />
        ))}
      </div>
    </section>
  );
}
