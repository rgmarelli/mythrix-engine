import type { Hotspot, HotspotMatch, HotspotSegment, Region, SignSummary, Source, Tradition } from '../api/types';

export function makeSource(overrides: Partial<Source> = {}): Source {
  return {
    id: 'source-1',
    domain: 'scripture',
    citation_label: 'Ecclesiasticus',
    title: 'Ecclesiasticus',
    author: 'Anonymous',
    publication_year: null,
    license: 'public-domain',
    uri: '',
    description: '',
    content_hash: 'abc123',
    ingested_at: null,
    ...overrides,
  };
}

export function makeSegment(overrides: Partial<HotspotSegment> = {}): HotspotSegment {
  return {
    ordinal: 1,
    locator: '43:1',
    text: 'The pride of the height, the clearness of the firmament.',
    section: '43',
    ...overrides,
  };
}

export function makeMatch(overrides: Partial<HotspotMatch> = {}): HotspotMatch {
  return {
    interpretant: 'sun',
    kind: 'concept',
    score: 0.82,
    exactValue: false,
    segmentOrdinal: 1,
    ...overrides,
  };
}

export function makeHotspot(overrides: Partial<Hotspot> = {}): Hotspot {
  return {
    regionId: 'region-1',
    source: makeSource(),
    locator: 'Ecclesiasticus 43:1',
    score: 0.82,
    convergenceCount: 1,
    segments: [makeSegment()],
    matches: [makeMatch()],
    ...overrides,
  };
}

export function makeRegion(overrides: Partial<Region> = {}): Region {
  return {
    region_id: 'region-1',
    source: makeSource(),
    locator: 'Ecclesiasticus 43:1',
    score: 0.82,
    convergence_count: 1,
    segments: [{ ordinal: 1, locator: '43:1', text: 'The pride of the height.', section: '43' }],
    matches: [{ interpretant: 'sun', kind: 'concept', score: 0.82, exact_value: false, segment_ordinal: 1 }],
    ...overrides,
  };
}

export function makeSignSummary(overrides: Partial<SignSummary> = {}): SignSummary {
  return {
    slug: 'the-sun',
    canonical_name: 'The Sun',
    sign_type: 'major-arcana',
    semiotic_system: 'tarot',
    tradition_slugs: ['rider-waite'],
    ...overrides,
  };
}

export function makeTradition(overrides: Partial<Tradition> = {}): Tradition {
  return {
    id: 'trad-1',
    slug: 'rider-waite',
    name: 'Rider-Waite',
    domain: 'tarot',
    description: '',
    ...overrides,
  };
}
