import type { Hotspot } from '../api/types';
import { convergenceLabel, hotspotTitle } from '../utils/hotspot';

interface Props {
  hotspot: Hotspot;
  isActive: boolean;
  onSelect: () => void;
}

export function HotspotCard({ hotspot, isActive, onSelect }: Props) {
  return (
    <button type="button" className={isActive ? 'hotspot-card active' : 'hotspot-card'} onClick={onSelect}>
      <div className="hotspot-card-header">
        <span className="title">{hotspotTitle(hotspot)}</span>
        <span className="badge">{convergenceLabel(hotspot.convergenceCount)}</span>
      </div>
      <span className="subtitle">{hotspot.matches.map((match) => match.interpretant).join(', ')}</span>
    </button>
  );
}
