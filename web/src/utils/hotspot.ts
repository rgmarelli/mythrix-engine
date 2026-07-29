import type { Hotspot, HotspotMatch, HotspotSegment } from '../api/types';

export function hotspotTitle(hotspot: Hotspot): string {
  return hotspot.locator || hotspot.source.citation_label || hotspot.source.title;
}

// Shared with `HotspotList`'s scroll-to-selection so both sides name the
// same DOM node without duplicating the id format.
export function hotspotElementId(regionId: string): string {
  return `hotspot-${regionId}`;
}

export function convergenceLabel(count: number): string {
  return `${count} interpretant${count === 1 ? '' : 's'}`;
}

/** The specific segment a match anchors to (FR-RK-09) — lets a consumer navigate
 * straight to where an interpretant hit, rather than re-scanning every
 * segment in the hotspot. */
export function segmentForMatch(hotspot: Hotspot, match: HotspotMatch): HotspotSegment | undefined {
  return hotspot.segments.find((segment) => segment.ordinal === match.segmentOrdinal);
}
