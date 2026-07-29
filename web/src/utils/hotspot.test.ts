// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import { convergenceLabel, hotspotTitle, segmentForMatch } from './hotspot';
import { makeHotspot, makeMatch, makeSegment, makeSource } from '../test/fixtures';

describe('hotspotTitle', () => {
  it('prefers the locator when present', () => {
    const hotspot = makeHotspot({ locator: 'Ecclesiasticus 43:1', source: makeSource({ citation_label: 'Eccl.', title: 'Ecclesiasticus' }) });
    expect(hotspotTitle(hotspot)).toBe('Ecclesiasticus 43:1');
  });

  it('falls back to the source citation label when locator is empty', () => {
    const hotspot = makeHotspot({ locator: '', source: makeSource({ citation_label: 'Eccl.', title: 'Ecclesiasticus' }) });
    expect(hotspotTitle(hotspot)).toBe('Eccl.');
  });

  it('falls back to the source title when locator and citation label are empty', () => {
    const hotspot = makeHotspot({ locator: '', source: makeSource({ citation_label: '', title: 'Ecclesiasticus' }) });
    expect(hotspotTitle(hotspot)).toBe('Ecclesiasticus');
  });
});

describe('convergenceLabel', () => {
  it('singularizes for a count of 1', () => {
    expect(convergenceLabel(1)).toBe('1 interpretant');
  });

  it('pluralizes for any other count', () => {
    expect(convergenceLabel(0)).toBe('0 interpretants');
    expect(convergenceLabel(3)).toBe('3 interpretants');
  });
});

describe('segmentForMatch', () => {
  it('finds the segment whose ordinal matches the match', () => {
    const segment = makeSegment({ ordinal: 5, text: 'target' });
    const hotspot = makeHotspot({ segments: [makeSegment({ ordinal: 1 }), segment] });
    const match = makeMatch({ segmentOrdinal: 5 });
    expect(segmentForMatch(hotspot, match)).toBe(segment);
  });

  it('returns undefined when no segment matches', () => {
    const hotspot = makeHotspot({ segments: [makeSegment({ ordinal: 1 })] });
    const match = makeMatch({ segmentOrdinal: 99 });
    expect(segmentForMatch(hotspot, match)).toBeUndefined();
  });
});
