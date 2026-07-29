// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import type { Hotspot } from '../api/types';
import { convergenceLabel, hotspotElementId, hotspotTitle } from '../utils/hotspot';
import { SparkleIcon } from './SparkleIcon';

interface Props {
  hotspot: Hotspot;
  isActive: boolean;
  isAugmented: boolean;
  onSelect: () => void;
}

export function HotspotCard({ hotspot, isActive, isAugmented, onSelect }: Props) {
  return (
    <button
      type="button"
      id={hotspotElementId(hotspot.regionId)}
      className={isActive ? 'hotspot-card active' : 'hotspot-card'}
      onClick={onSelect}
    >
      <div className="hc-top">
        <span className="hc-title">
          {hotspotTitle(hotspot)}
          {/* The reading itself stays in the reader; the rail only says one
              exists (specs/interfaces/augmentation.md FR-AU-27). */}
          {isAugmented && (
            <span className="augmented-mark" title="Has AI analysis">
              <SparkleIcon />
            </span>
          )}
        </span>
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
