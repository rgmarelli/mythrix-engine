// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect } from 'react';
import type { ReactNode } from 'react';
import type { Augmentation, Hotspot } from '../api/types';
import { hotspotElementId } from '../utils/hotspot';
import { ConvergenceIcon } from './ConvergenceIcon';
import { HotspotCard } from './HotspotCard';

interface Props {
  headerText: ReactNode;
  hasResult: boolean;
  hotspots: Hotspot[];
  selectedRegionId: string | null;
  search: string;
  augmentations: Record<string, Augmentation>;
  onSearchChange: (value: string) => void;
  onSelect: (regionId: string) => void;
}

export function HotspotList({
  headerText,
  hasResult,
  hotspots,
  selectedRegionId,
  search,
  augmentations,
  onSearchChange,
  onSelect,
}: Props) {
  // Brings the selected card into view when selection changes from outside
  // this list (specs/interfaces/web-viewer.md FR-WEB-30) — e.g. a chat
  // marker click. `block: 'nearest'` is a no-op when the card is already
  // visible, so this is safe on every selection change, including an
  // ordinary click on a card already in view.
  useEffect(() => {
    if (!selectedRegionId) return;
    document.getElementById(hotspotElementId(selectedRegionId))?.scrollIntoView({ block: 'nearest' });
  }, [selectedRegionId]);

  return (
    <section className="hotspot-rail">
      {hasResult && (
        <div className="facet-search">
          <svg viewBox="0 0 24 24" fill="none">
            <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.8" />
            <path d="M21 21l-4.3-4.3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          <input
            type="text"
            value={search}
            placeholder="Filter hotspots…"
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </div>
      )}
      {hasResult && <div className="rail-header">{headerText}</div>}
      {!hasResult && (
        <div className="rail-empty-state">
          <ConvergenceIcon />
          <strong>No query yet</strong>
          <p>Set a system, sign and tradition on the left, then press "Explore" to see semantic hotspots here.</p>
        </div>
      )}
      {hasResult && hotspots.length === 0 && (
        <div className="rail-empty-state">
          <ConvergenceIcon />
          <strong>No matches</strong>
          <p>No hotspots match the current filters — try widening the source, interpretant, or search.</p>
        </div>
      )}
      {hasResult &&
        hotspots.map((hotspot) => (
          <HotspotCard
            key={hotspot.regionId}
            hotspot={hotspot}
            isActive={hotspot.regionId === selectedRegionId}
            isAugmented={hotspot.regionId in augmentations}
            onSelect={() => onSelect(hotspot.regionId)}
          />
        ))}
    </section>
  );
}
