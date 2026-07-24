import type { Hotspot } from '../api/types';
import { HotspotCard } from './HotspotCard';

interface Props {
  headerText: string;
  hotspots: Hotspot[];
  selectedRegionId: string | null;
  onSelect: (regionId: string) => void;
}

export function HotspotList({ headerText, hotspots, selectedRegionId, onSelect }: Props) {
  return (
    <section className="hotspot-rail">
      <div className="rail-header">{headerText}</div>
      {hotspots.length === 0 && <p className="rail-empty">No hotspots match the current filters.</p>}
      {hotspots.map((hotspot) => (
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
