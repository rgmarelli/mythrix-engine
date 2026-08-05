// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import { fetchCapabilities, fetchQuery, fetchSegments, fetchSigns, fetchTraditions, streamAgentTurn } from './client';
import type { AgentTurnResponseWire, RegionQueryResult } from './types';
import { makeRegion, makeSignSummary, makeTradition } from '../test/fixtures';

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: () => Promise.resolve(body),
  } as Response;
}

// An NDJSON body delivered as the given raw chunks, so a test can put a chunk
// boundary anywhere — including mid-line, which is the case the reader's
// buffering exists for.
function ndjsonResponse(chunks: string[], ok = true, status = 200): Response {
  const encoder = new TextEncoder();
  let index = 0;
  return {
    ok,
    status,
    json: () => Promise.resolve(null),
    body: {
      getReader: () => ({
        read: () =>
          Promise.resolve(
            index < chunks.length ? { done: false, value: encoder.encode(chunks[index++]) } : { done: true },
          ),
      }),
    },
  } as unknown as Response;
}

function ndjsonLines(...events: unknown[]): Response {
  return ndjsonResponse(events.map((event) => `${JSON.stringify(event)}\n`));
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('fetchTraditions', () => {
  it('GETs /api/traditions and returns the parsed list', async () => {
    const traditions = [makeTradition()];
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(traditions));
    const result = await fetchTraditions();
    expect(fetch).toHaveBeenCalledWith('/api/traditions');
    expect(result).toEqual(traditions);
  });
});

describe('fetchSigns', () => {
  it('GETs /api/signs and returns the parsed list', async () => {
    const signs = [makeSignSummary()];
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(signs));
    const result = await fetchSigns();
    expect(fetch).toHaveBeenCalledWith('/api/signs');
    expect(result).toEqual(signs);
  });
});

describe('fetchQuery', () => {
  it('encodes sign/tradition/opts as query params', async () => {
    const wire: RegionQueryResult = { facets: { sources: [], interpretants: [] }, regions: [] };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(wire));
    await fetchQuery('the-sun', 'rider-waite', { matchPool: 50, minScore: 0.5 });
    const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(calledUrl).toContain('/api/query?');
    expect(calledUrl).toContain('sign=the-sun');
    expect(calledUrl).toContain('tradition=rider-waite');
    expect(calledUrl).toContain('match_pool=50');
    expect(calledUrl).toContain('min_score=0.5');
  });

  it('omits optional params when not supplied', async () => {
    const wire: RegionQueryResult = { facets: { sources: [], interpretants: [] }, regions: [] };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(wire));
    await fetchQuery('the-sun', 'rider-waite');
    const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(calledUrl).not.toContain('match_pool');
    expect(calledUrl).not.toContain('min_score');
  });

  it('translates wire regions to camelCase hotspots', async () => {
    const region = makeRegion();
    const wire: RegionQueryResult = { facets: { sources: [], interpretants: [] }, regions: [region] };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(wire));
    const result = await fetchQuery('the-sun', 'rider-waite');
    expect(result.hotspots).toHaveLength(1);
    const hotspot = result.hotspots[0];
    expect(hotspot.regionId).toBe(region.region_id);
    expect(hotspot.convergenceCount).toBe(region.convergence_count);
    expect(hotspot.matches[0]).toEqual({
      interpretant: 'sun',
      kind: 'concept',
      score: 0.82,
      exactValue: false,
      segmentOrdinal: 1,
    });
  });

  it('throws the response detail message on a non-ok response', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'sign not found' }, false, 404));
    await expect(fetchQuery('missing', 'rider-waite')).rejects.toThrow('sign not found');
  });

  it('falls back to a generic message when the error body has no detail', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(null, false, 500));
    await expect(fetchQuery('the-sun', 'rider-waite')).rejects.toThrow('Query failed (500)');
  });
});

describe('fetchSegments', () => {
  it('encodes source/ordinal range as query params', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse([]));
    await fetchSegments('source-1', 3, 7);
    const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(calledUrl).toContain('/api/segments?');
    expect(calledUrl).toContain('source_id=source-1');
    expect(calledUrl).toContain('start_ordinal=3');
    expect(calledUrl).toContain('end_ordinal=7');
  });

  it('throws the response detail message on a non-ok response', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'bad range' }, false, 400));
    await expect(fetchSegments('source-1', 3, 7)).rejects.toThrow('bad range');
  });
});

describe('streamAgentTurn', () => {
  const uiSelection = {
    semioticSystem: 'tarot',
    sign: 'the-sun',
    tradition: 'rider-waite',
    interpretant: null,
    minScore: null,
    regionId: 'region-1',
    locator: 'Ecclesiasticus 43:1',
    extendedRegionId: null,
    extendedLocator: null,
  };

  const turnEvent: AgentTurnResponseWire = {
    event: 'turn',
    context: {
      semiotic_system: 'tarot',
      sign: 'the-sun',
      tradition: 'rider-waite',
      interpretant: null,
      min_score: null,
      region_id: 'region-1',
      locator: 'Ecclesiasticus 43:1',
      extended_region_id: null,
      extended_locator: null,
    },
    reply_text: 'hello',
    instructions: [],
    thread_reset: false,
  };

  it('POSTs a snake_case request body carrying the visible regions', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(ndjsonLines(turnEvent));

    await streamAgentTurn('session-1', 'hi', uiSelection, ['src::1-2', 'src::5-6']);

    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe('/api/agent');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({
      session_id: 'session-1',
      message: 'hi',
      ui_selection: {
        semiotic_system: 'tarot',
        sign: 'the-sun',
        tradition: 'rider-waite',
        interpretant: null,
        min_score: null,
        region_id: 'region-1',
        locator: 'Ecclesiasticus 43:1',
        extended_region_id: null,
        extended_locator: null,
      },
      visible_regions: ['src::1-2', 'src::5-6'],
    });
  });

  it('returns the terminal event, translated', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(ndjsonLines({ ...turnEvent, thread_reset: true }));

    const result = await streamAgentTurn('session-1', 'hi', uiSelection, []);

    expect(result.replyText).toBe('hello');
    expect(result.threadReset).toBe(true);
    expect(result.context.regionId).toBe('region-1');
  });

  it('delivers each non-terminal event to onEvent, in order', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      ndjsonLines(
        { event: 'message', text: 'Augmented [R1] Douay-Rheims — Genesis 21:6' },
        { event: 'instruction', instruction: { type: 'augment_region', payload: { region_id: 'src::1-2' } } },
        turnEvent,
      ),
    );
    const seen: string[] = [];

    await streamAgentTurn('session-1', 'hi', uiSelection, [], (event) => seen.push(event.event));

    expect(seen).toEqual(['message', 'instruction']);
  });

  it('parses a line split across two chunks', async () => {
    const line = `${JSON.stringify(turnEvent)}\n`;
    const cut = Math.floor(line.length / 2);
    vi.mocked(fetch).mockResolvedValueOnce(ndjsonResponse([line.slice(0, cut), line.slice(cut)]));

    const result = await streamAgentTurn('session-1', 'hi', uiSelection, []);

    expect(result.replyText).toBe('hello');
  });

  it('delivers a final line that arrived without a trailing newline', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(ndjsonResponse([JSON.stringify(turnEvent)]));

    const result = await streamAgentTurn('session-1', 'hi', uiSelection, []);

    expect(result.replyText).toBe('hello');
  });

  it('throws when the stream ends without a terminal event', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(ndjsonLines({ event: 'message', text: 'started…' }));

    await expect(streamAgentTurn('session-1', 'hi', uiSelection, [])).rejects.toThrow('without completing');
  });

  it('throws the response detail message on a non-ok response', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'agent unavailable' }, false, 503));

    await expect(streamAgentTurn('session-1', 'hi', uiSelection, [])).rejects.toThrow('agent unavailable');
  });
});

describe('fetchCapabilities', () => {
  const wire = {
    commands: [
      { name: '/clear', args: null, summary: 'Clear this thread', handled_by: 'client', listed: true },
      { name: '/query', args: 'term, …', summary: 'Search', handled_by: 'server', listed: true },
    ],
    instructions: [
      { type: 'confirm_query', binding: null },
      { type: 'execute_query', binding: { method: 'QUERY', path: '/api/query/adhoc', body: 'payload', result: 'regions' } },
    ],
  };

  it('GETs /api/agent/capabilities and maps commands and bindings', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(wire));
    const result = await fetchCapabilities();
    expect(fetch).toHaveBeenCalledWith('/api/agent/capabilities');
    expect(result.commands[0]).toEqual({
      name: '/clear',
      args: null,
      summary: 'Clear this thread',
      handledBy: 'client',
      listed: true,
    });
    expect(result.bindings.execute_query).toEqual({
      method: 'QUERY',
      path: '/api/query/adhoc',
      body: 'payload',
      result: 'regions',
    });
  });

  it('keeps a declared-but-unbound type as null, distinct from an absent one', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(wire));
    const result = await fetchCapabilities();
    expect(result.bindings.confirm_query).toBeNull();
    expect('confirm_query' in result.bindings).toBe(true);
    expect('something_else' in result.bindings).toBe(false);
  });

  it.each([
    ['an unsafe method', { method: 'POST', path: '/api/query/adhoc', body: 'payload', result: 'regions' }],
    ['an unknown method', { method: 'BREW', path: '/api/query/adhoc', body: 'payload', result: 'regions' }],
    ['an absolute URL', { method: 'QUERY', path: 'https://evil.test/x', body: 'payload', result: 'regions' }],
    ['a protocol-relative path', { method: 'QUERY', path: '//evil.test/x', body: 'payload', result: 'regions' }],
    ['an unknown body mode', { method: 'QUERY', path: '/api/query/adhoc', body: 'template', result: 'regions' }],
    ['an unknown result kind', { method: 'QUERY', path: '/api/query/adhoc', body: 'payload', result: 'chart' }],
  ])('drops a binding naming %s', async (_label, binding) => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ commands: [], instructions: [{ type: 'execute_query', binding }] }),
    );
    const result = await fetchCapabilities();
    // Dropped entirely, not stored as null: an unusable binding must not read
    // as "declared with nothing to call".
    expect('execute_query' in result.bindings).toBe(false);
  });
});
