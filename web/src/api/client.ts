// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import type {
  AgentCapabilities,
  AgentCapabilitiesWire,
  AgentContext,
  AgentInstructionEventWire,
  AgentMessageEventWire,
  AgentTurnEventWire,
  AgentTurnRequestWire,
  AgentTurnResponseWire,
  AgentTurnResult,
  BodyMode,
  ExtendedRegion,
  ExtendedRegionWire,
  Hotspot,
  HotspotQueryResult,
  HotspotSegment,
  InstructionBinding,
  InstructionBindingWire,
  Region,
  RegionQueryResult,
  ResultKind,
  SafeMethod,
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
  opts?: { matchPool?: number; minScore?: number },
): Promise<HotspotQueryResult> {
  const params = new URLSearchParams({ sign, tradition });
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

// One Add Context activation over `[startOrdinal, endOrdinal]` — the
// server-side boundary logic behind the Add Context action, replacing this
// app's own client-side edge-probing/gap-detection logic. `loadedCount` is
// how many
// segments the caller currently holds in that range — fewer than the range's
// full span means an internal gap remains, which this activation fills
// (and only that); otherwise it extends the window by one segment past each
// edge that can still extend (FR-CE-02/03).
export async function extendContext(
  sourceId: string,
  startOrdinal: number,
  endOrdinal: number,
  loadedCount: number,
): Promise<ExtendedRegion> {
  const params = new URLSearchParams({
    source_id: sourceId,
    start_ordinal: String(startOrdinal),
    end_ordinal: String(endOrdinal),
    loaded_count: String(loadedCount),
  });
  const response = await fetch(`${API_BASE_URL}/api/regions/extend-context?${params.toString()}`);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Extend-context request failed (${response.status})`);
  }
  const wire = (await response.json()) as ExtendedRegionWire;
  return {
    regionId: wire.region_id,
    locator: wire.locator,
    segments: wire.segments.map((segment) => ({ ...segment })),
    leadingBounded: wire.leading_bounded,
    trailingBounded: wire.trailing_bounded,
  };
}

const SAFE_METHODS: SafeMethod[] = ['GET', 'QUERY'];
const BODY_MODES: BodyMode[] = ['payload'];
const RESULT_KINDS: ResultKind[] = ['regions'];

// A path this app will actually dial: same-origin and absolute (FR-CAP-09).
// `//host` is rejected explicitly — it is protocol-relative, so it leaves the
// origin despite starting with a slash.
function isSameOriginPath(path: string): boolean {
  return path.startsWith('/') && !path.startsWith('//');
}

// Bindings are validated here, at the seam, rather than at the point of use:
// a binding that survives this function is executable, so no later code has to
// re-ask. A binding that fails becomes `undefined` — reported as unexecutable
// (FR-CAP-13) rather than silently treated as "no binding needed".
function toBinding(wire: InstructionBindingWire | null): InstructionBinding | null | undefined {
  if (wire === null) return null;
  const method = SAFE_METHODS.find((candidate) => candidate === wire.method);
  const body = BODY_MODES.find((candidate) => candidate === wire.body);
  const result = RESULT_KINDS.find((candidate) => candidate === wire.result);
  if (!method || !body || !result || !isSameOriginPath(wire.path)) return undefined;
  return { method, path: wire.path, body, result };
}

function toCapabilities(wire: AgentCapabilitiesWire): AgentCapabilities {
  const bindings: Record<string, InstructionBinding | null> = {};
  for (const instruction of wire.instructions) {
    const binding = toBinding(instruction.binding);
    if (binding !== undefined) bindings[instruction.type] = binding;
  }
  return {
    commands: wire.commands.map((command) => ({
      name: command.name,
      args: command.args,
      summary: command.summary,
      handledBy: command.handled_by,
      listed: command.listed,
    })),
    bindings,
  };
}

// Fetched once per application load (FR-CAP-03) — it describes the running
// build, not a caller or a session.
export async function fetchCapabilities(): Promise<AgentCapabilities> {
  return toCapabilities(await fetchJson<AgentCapabilitiesWire>('/api/agent/capabilities'));
}

// Issues the request a binding declares, with the instruction's payload as the
// body (FR-CAP-12), and maps the result through the same `toHotspot` seam
// `fetchQuery` uses — so an ad-hoc result and a graph-native one are the same
// shape by construction, not by coincidence.
export async function fetchBoundRegions(
  binding: InstructionBinding,
  payload: Record<string, unknown>,
): Promise<HotspotQueryResult> {
  const response = await fetch(`${API_BASE_URL}${binding.path}`, {
    method: binding.method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Query failed (${response.status})`);
  }
  const result = (await response.json()) as RegionQueryResult;
  return { facets: result.facets, hotspots: result.regions.map(toHotspot) };
}

function toAgentContextWire(selection: AgentContext) {
  return {
    semiotic_system: selection.semioticSystem,
    sign: selection.sign,
    tradition: selection.tradition,
    interpretant: selection.interpretant,
    min_score: selection.minScore,
    region_id: selection.regionId,
    locator: selection.locator,
    extended_region_id: selection.extendedRegionId,
    extended_locator: selection.extendedLocator,
  };
}

function toAgentContext(wire: AgentTurnResponseWire['context']): AgentContext {
  return {
    semioticSystem: wire.semiotic_system,
    sign: wire.sign,
    tradition: wire.tradition,
    interpretant: wire.interpretant,
    minScore: wire.min_score,
    regionId: wire.region_id,
    locator: wire.locator,
    extendedRegionId: wire.extended_region_id,
    extendedLocator: wire.extended_locator,
  };
}

// Splits a byte stream into complete newline-delimited JSON values. A chunk
// boundary can fall anywhere — including mid-line — so the partial tail is
// buffered rather than parsed, and whatever remains after the stream closes is
// delivered if the body did not end with a newline.
async function* ndjson<T>(body: ReadableStream<Uint8Array>): AsyncGenerator<T> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (line.trim()) yield JSON.parse(line) as T;
    }
  }
  if (buffer.trim()) yield JSON.parse(buffer) as T;
}

// The chat panel's one turn (specs/interfaces/agent.md FR-AG-14–FR-AG-22) — the
// browser sends its message, its current UI selection and the regions it is
// displaying, as-is, each turn; the backend streams the turn's events
// (augmentation.md FR-AU-22).
//
// `onEvent` receives every non-terminal event as it arrives; the terminal one
// is returned, so a caller that only wants the reply can ignore the callback
// entirely and still read this like an ordinary request.
export async function streamAgentTurn(
  sessionId: string,
  message: string,
  uiSelection: AgentContext,
  visibleRegions: string[],
  onEvent?: (event: AgentMessageEventWire | AgentInstructionEventWire) => void,
): Promise<AgentTurnResult> {
  const requestBody: AgentTurnRequestWire = {
    session_id: sessionId,
    message,
    ui_selection: toAgentContextWire(uiSelection),
    visible_regions: visibleRegions,
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
  if (!response.body) throw new Error('Agent request returned no body.');

  let terminal: AgentTurnResponseWire | null = null;
  for await (const event of ndjson<AgentTurnEventWire>(response.body)) {
    if (event.event === 'turn') {
      terminal = event;
      continue;
    }
    onEvent?.(event);
  }
  if (!terminal) throw new Error('Agent request ended without completing the turn.');

  return {
    context: toAgentContext(terminal.context),
    replyText: terminal.reply_text,
    instructions: terminal.instructions,
    threadReset: terminal.thread_reset,
  };
}
