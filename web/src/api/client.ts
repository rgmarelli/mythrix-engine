import type { FragmentQueryResult, SignSummary, Tradition } from './types';

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

export async function fetchQuery(
  symbol: string,
  tradition: string,
  opts?: { topK?: number; matchPool?: number },
): Promise<FragmentQueryResult> {
  const params = new URLSearchParams({ symbol, tradition });
  if (opts?.topK !== undefined) params.set('top_k', String(opts.topK));
  if (opts?.matchPool !== undefined) params.set('match_pool', String(opts.matchPool));

  const response = await fetch(`${API_BASE_URL}/api/query?${params.toString()}`);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Query failed (${response.status})`);
  }
  return response.json() as Promise<FragmentQueryResult>;
}
