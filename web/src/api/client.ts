import type {
  AgentCard,
  AgentCardWire,
  AgentContext,
  AgentTurnRequestWire,
  AgentTurnResponseWire,
  AgentTurnResult,
  AgentUiSelection,
  Hotspot,
  HotspotQueryResult,
  HotspotSegment,
  Region,
  RegionQueryResult,
  SignSummary,
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

export function fetchSigns(): Promise<SignSummary[]> {
  return fetchJson('/api/signs');
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
  sign: string,
  tradition: string,
  opts?: { topK?: number; matchPool?: number; minScore?: number },
): Promise<HotspotQueryResult> {
  const params = new URLSearchParams({ sign, tradition });
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

// Coordinate-based range lookup behind the Add Context action
// (specs/retrieval/context-expansion.md) — no query embedding, no
// similarity ranking; distinct from `fetchQuery`.
export async function fetchSegments(
  sourceId: string,
  startOrdinal: number,
  endOrdinal: number,
): Promise<HotspotSegment[]> {
  const params = new URLSearchParams({
    source_id: sourceId,
    start_ordinal: String(startOrdinal),
    end_ordinal: String(endOrdinal),
  });
  const response = await fetch(`${API_BASE_URL}/api/segments?${params.toString()}`);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Segments request failed (${response.status})`);
  }
  return response.json() as Promise<HotspotSegment[]>;
}

function toAgentUiSelectionWire(selection: AgentUiSelection) {
  return {
    semiotic_system: selection.semioticSystem,
    sign: selection.sign,
    tradition: selection.tradition,
    source_id: selection.sourceId,
    interpretant: selection.interpretant,
    min_score: selection.minScore,
    region_id: selection.regionId,
    locator: selection.locator,
  };
}

function toAgentContext(wire: AgentTurnResponseWire['context']): AgentContext {
  return {
    semioticSystem: wire.semiotic_system,
    sign: wire.sign,
    tradition: wire.tradition,
    sourceId: wire.source_id,
    interpretant: wire.interpretant,
    minScore: wire.min_score,
    regionId: wire.region_id,
    locator: wire.locator,
  };
}

function toAgentCard(card: AgentCardWire): AgentCard {
  if (card.type === 'interpretant_chips') {
    return {
      type: 'interpretant_chips',
      chips: (card.chips ?? []).map((chip) => ({
        interpretant: chip.interpretant,
        kind: chip.kind,
        score: chip.score,
        segmentOrdinal: chip.segment_ordinal,
      })),
    };
  }
  return { type: 'citation', sourceLabel: card.source_label ?? '', locator: card.locator ?? '', text: card.text ?? '' };
}

// The chat panel's one turn (specs/interfaces/agent.md FR-AG-14–FR-AG-22) — the browser sends
// its message plus its current UI selection, as-is, each turn; the backend
// returns the updated context, grounded reply text, and structured cards.
export async function postAgentTurn(
  sessionId: string,
  message: string,
  uiSelection: AgentUiSelection,
): Promise<AgentTurnResult> {
  const requestBody: AgentTurnRequestWire = {
    session_id: sessionId,
    message,
    ui_selection: toAgentUiSelectionWire(uiSelection),
  };
  const response = await fetch(`${API_BASE_URL}/api/agent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Agent request failed (${response.status})`);
  }
  const result = (await response.json()) as AgentTurnResponseWire;
  return {
    context: toAgentContext(result.context),
    replyText: result.reply_text,
    cards: result.cards.map(toAgentCard),
    threadReset: result.thread_reset,
  };
}
