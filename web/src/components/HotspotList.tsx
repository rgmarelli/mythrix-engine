import type { Hotspot } from '../api/types';
import { ConvergenceIcon } from './ConvergenceIcon';
import { HotspotCard } from './HotspotCard';

interface Props {
  headerText: string;
  hasResult: boolean;
  hotspots: Hotspot[];
  selectedRegionId: string | null;
  onSelect: (regionId: string) => void;
}

export function HotspotList({ headerText, hasResult, hotspots, selectedRegionId, onSelect }: Props) {
  return (
    <section className="hotspot-rail">
      {hasResult && <div className="rail-header">{headerText}</div>}
      {!hasResult && (
        <div className="rail-empty-state">
          <ConvergenceIcon />
          <strong>No query yet</strong>
          <p>Set a system, symbol and tradition on the left, then press "Explore" to see semantic hotspots here.</p>
        </div>
      )}
      {hasResult && hotspots.length === 0 && (
        <div className="rail-empty-state">
          <ConvergenceIcon />
          <strong>No matches</strong>
          <p>No hotspots match the current filters — try widening the source or interpretant selection.</p>
        </div>
      )}
      {hasResult &&
        hotspots.map((hotspot) => (
          <HotspotCard
            key={hotspot.regionId}
            hotspot={hotspot}
            isActive={hotspot.regionId === selectedRegionId}
            onSelect={() => onSelect(hotspot.regionId)}
          />
        ))}
    </section>
  );
}
