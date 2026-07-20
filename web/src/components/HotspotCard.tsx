import type { Fragment } from '../api/types';
import { convergenceLabel, fragmentTitle } from '../utils/fragment';

interface Props {
  fragment: Fragment;
  isActive: boolean;
  onSelect: () => void;
}

export function HotspotCard({ fragment, isActive, onSelect }: Props) {
  return (
    <button type="button" className={isActive ? 'hotspot-card active' : 'hotspot-card'} onClick={onSelect}>
      <div className="hotspot-card-header">
        <span className="title">{fragmentTitle(fragment)}</span>
        <span className="badge">{convergenceLabel(fragment.convergence_count)}</span>
      </div>
      <span className="subtitle">{fragment.matches.map((match) => match.interpretant).join(', ')}</span>
    </button>
  );
}
