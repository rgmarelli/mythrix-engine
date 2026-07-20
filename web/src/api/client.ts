import type {
  ConceptCandidates,
  ConceptPairCandidates,
  GraphFacts,
  SymbolSummary,
  Tradition,
} from './types';

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

export function fetchSymbols(): Promise<SymbolSummary[]> {
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

export interface QueryStreamHandlers {
  onGraphFacts: (data: GraphFacts) => void;
  onConceptCandidates: (data: ConceptCandidates) => void;
  onPairCandidates: (data: ConceptPairCandidates) => void;
  onDone: () => void;
  onError: (message: string) => void;
}

/** Opens the `GET /api/query` SSE stream and wires each named event to its
 * handler. Returns a function that closes the connection early (component
 * unmount, or a new query submitted before this one finished).
 *
 * `EventSource`'s native `error` event and the server's own named `event:
 * error` are indistinguishable at the browser API level — both dispatch on
 * the `'error'` listener. A server-sent `event: error` arrives as a
 * `MessageEvent` carrying `.data`; a connection-level failure (network
 * error, or — the pre-stream FR9 case, an unknown symbol/tradition — a
 * non-2xx response before the stream opens) arrives as a plain `Event`
 * with no `.data`, and its response body is never exposed to this code by
 * the `EventSource` API, so that case falls back to a generic message. In
 * practice this path is a fallback only: `SymbolTraditionPicker` already
 * restricts submissions to symbol/tradition pairs `/api/symbols` reports
 * as valid. */
export function streamQuery(
  symbol: string,
  tradition: string,
  handlers: QueryStreamHandlers,
): () => void {
  const url = new URL(`${API_BASE_URL}/api/query`, window.location.origin);
  url.searchParams.set('symbol', symbol);
  url.searchParams.set('tradition', tradition);

  const source = new EventSource(url);

  source.addEventListener('graph_facts', (event) => {
    handlers.onGraphFacts(JSON.parse((event as MessageEvent).data) as GraphFacts);
  });
  source.addEventListener('concept_candidates', (event) => {
    handlers.onConceptCandidates(JSON.parse((event as MessageEvent).data) as ConceptCandidates);
  });
  source.addEventListener('pair_candidates', (event) => {
    handlers.onPairCandidates(JSON.parse((event as MessageEvent).data) as ConceptPairCandidates);
  });
  source.addEventListener('done', () => {
    handlers.onDone();
    source.close();
  });
  source.addEventListener('error', (event) => {
    if (event instanceof MessageEvent && typeof event.data === 'string') {
      try {
        const payload = JSON.parse(event.data) as { detail: string };
        handlers.onError(payload.detail);
      } catch {
        handlers.onError('The server reported an error retrieving this query.');
      }
    } else {
      handlers.onError('Could not reach the server, or the symbol/tradition pair is invalid.');
    }
    source.close();
  });

  return () => source.close();
}
