import type { Hotspot, HotspotQueryResult, Region, RegionQueryResult, SignSummary, Tradition } from './types';

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '';

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`Request to ${path} failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function fetchTraditions(): Promise<Tradition[]> {
  return fetchJson('/api/traditions');
}

export function fetchSymbols(): Promise<SignSummary[]> {
  return fetchJson('/api/symbols');
}

export async function summarizePassage(passageText: string, concepts: string[]): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/summarize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ passage_text: passageText, concepts }),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Summarize request failed (${response.status})`);
  }
  const data = (await response.json()) as { summary: string };
  return data.summary;
}

// The single seam translating the wire `Region` shape (snake_case, as
// `RegionQueryResult.model_dump(mode="json")` sends it) onto this app's
// `Hotspot` view model (camelCase, existing component vocabulary) — every
// other call site works with `Hotspot`/`HotspotMatch`/`HotspotSegment` only.
function toHotspot(region: Region): Hotspot {
  return {
    regionId: region.region_id,
    source: region.source,
    locator: region.locator,
    score: region.score,
    convergenceCount: region.convergence_count,
    segments: region.segments.map((segment) => ({ ...segment })),
    matches: region.matches.map((match) => ({
      interpretant: match.interpretant,
      kind: match.kind,
      score: match.score,
      exactValue: match.exact_value,
      segmentOrdinal: match.segment_ordinal,
    })),
  };
}

export async function fetchQuery(
  symbol: string,
  tradition: string,
  opts?: { topK?: number; matchPool?: number; minScore?: number },
): Promise<HotspotQueryResult> {
  const params = new URLSearchParams({ symbol, tradition });
  if (opts?.topK !== undefined) params.set('top_k', String(opts.topK));
  if (opts?.matchPool !== undefined) params.set('match_pool', String(opts.matchPool));
  if (opts?.minScore !== undefined) params.set('min_score', String(opts.minScore));

  const response = await fetch(`${API_BASE_URL}/api/query?${params.toString()}`);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Query failed (${response.status})`);
  }
  const result = (await response.json()) as RegionQueryResult;
  return { facets: result.facets, hotspots: result.regions.map(toHotspot) };
}
