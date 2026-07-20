import type { RetrievedPassage } from '../api/types';

interface Props {
  passage: RetrievedPassage;
  scoreLabel: string;
  isSelected: boolean;
  onSelect: (passage: RetrievedPassage) => void;
}

/** Metadata only — source attribution and score, never `passage.text` (FR4).
 * The only way to see any passage text is to select a card, which shows the
 * full record in `PassageDetailPanel`. Attribution mirrors
 * `cli/formatting.py`'s formula: `citation_label`, falling back to
 * `title, author` when a source has none. */
export function PassageCard({ passage, scoreLabel, isSelected, onSelect }: Props) {
  const attribution = passage.source.citation_label || `${passage.source.title}, ${passage.source.author}`;
  return (
    <button
      type="button"
      className={isSelected ? 'passage-card selected' : 'passage-card'}
      onClick={() => onSelect(passage)}
    >
      <span className="attribution">
        {attribution}
        {passage.locator && ` - ${passage.locator}`}
      </span>
      <span className="score">{scoreLabel}</span>
      <span className="hint">click to view →</span>
    </button>
  );
}
