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
      <div className="hc-top">
        <span className="hc-title">{hotspotTitle(hotspot)}</span>
        <span className="hc-badge">{convergenceLabel(hotspot.convergenceCount)}</span>
      </div>
      <span className="hc-source">{hotspot.source.citation_label || hotspot.source.title}</span>
      <div className="hc-dots">
        {hotspot.matches.map((match) => (
          <span className="conv-chip" key={`${match.interpretant}-${match.segmentOrdinal}`}>
            {match.interpretant} · {match.kind === 'concept' ? match.score.toFixed(2) : match.kind}
          </span>
        ))}
      </div>
    </button>
  );
}
