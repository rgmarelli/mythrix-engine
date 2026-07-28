import { executeInstruction } from './instructions';
import type { AgentCapabilities, AgentInstruction, RegionQueryResult } from './types';
import { makeRegion } from '../test/fixtures';

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return { ok, status, json: () => Promise.resolve(body) } as Response;
}

const CAPABILITIES: AgentCapabilities = {
  commands: [],
  bindings: {
    confirm_query: null,
    execute_query: { method: 'QUERY', path: '/api/query/adhoc', body: 'payload', result: 'regions' },
  },
};

const EXECUTE: AgentInstruction = { type: 'execute_query', payload: { terms: [{ value: 'laughter', directive: null }] } };

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

it('issues the declared request with the payload as body and maps regions to hotspots', async () => {
  const wire: RegionQueryResult = { facets: { sources: [], interpretants: [] }, regions: [makeRegion()] };
  vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(wire));

  const outcome = await executeInstruction(EXECUTE, CAPABILITIES);

  expect(fetch).toHaveBeenCalledWith('/api/query/adhoc', {
    method: 'QUERY',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(EXECUTE.payload),
  });
  expect(outcome).toEqual({
    kind: 'regions',
    result: { facets: wire.facets, hotspots: [expect.objectContaining({ regionId: wire.regions[0].region_id })] },
  });
});

it('returns null for a type declared with no binding — nothing to run, nothing wrong', async () => {
  const outcome = await executeInstruction({ type: 'confirm_query', payload: {} }, CAPABILITIES);

  expect(outcome).toBeNull();
  expect(fetch).not.toHaveBeenCalled();
});

it('reports an undeclared type as unexecutable without issuing a request', async () => {
  const outcome = await executeInstruction({ type: 'render_chart', payload: {} }, CAPABILITIES);

  expect(outcome?.kind).toBe('unexecutable');
  expect(fetch).not.toHaveBeenCalled();
});

it('reports as unexecutable when no capabilities loaded, rather than guessing an endpoint', async () => {
  const outcome = await executeInstruction(EXECUTE, null);

  expect(outcome?.kind).toBe('unexecutable');
  expect(fetch).not.toHaveBeenCalled();
});

it('reports a failed request as unexecutable, carrying the server detail', async () => {
  vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'no terms given' }, false, 422));

  const outcome = await executeInstruction(EXECUTE, CAPABILITIES);

  expect(outcome).toEqual({ kind: 'unexecutable', reason: 'no terms given' });
});
