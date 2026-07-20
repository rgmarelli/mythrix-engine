import type { Fragment } from '../api/types';
import { HotspotCard } from './HotspotCard';

interface Props {
  headerText: string;
  fragments: Fragment[];
  selectedChunkId: string | null;
  onSelect: (chunkId: string) => void;
}

export function HotspotList({ headerText, fragments, selectedChunkId, onSelect }: Props) {
  return (
    <section className="hotspot-list">
      <h2>{headerText}</h2>
      {fragments.length === 0 && <p className="empty">No fragments match the current filters.</p>}
      {fragments.map((fragment) => (
        <HotspotCard
          key={fragment.chunk_id}
          fragment={fragment}
          isActive={fragment.chunk_id === selectedChunkId}
          onSelect={() => onSelect(fragment.chunk_id)}
        />
      ))}
    </section>
  );
}
