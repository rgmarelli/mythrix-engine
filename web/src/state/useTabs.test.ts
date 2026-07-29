import { act, renderHook, waitFor } from '@testing-library/react';
import { fetchBoundRegions, fetchQuery, postAgentTurn } from '../api/client';
import { DEFAULT_MIN_SCORE, useTabs } from './useTabs';
import { makeHotspot } from '../test/fixtures';
import type { AgentCapabilities, AgentInstruction, HotspotQueryResult } from '../api/types';

vi.mock('../api/client', () => ({
  fetchQuery: vi.fn(),
  postAgentTurn: vi.fn(),
  fetchBoundRegions: vi.fn(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

it('exports the documented default min score', () => {
  expect(DEFAULT_MIN_SCORE).toBe(0.6);
});

describe('tab lifecycle', () => {
  it('starts with exactly one empty tab', () => {
    const { result } = renderHook(() => useTabs());
    expect(result.current.tabs).toHaveLength(1);
    expect(result.current.activeTab.selectedSign).toBe('');
  });

  it('addTab appends a new tab and makes it active', () => {
    const { result } = renderHook(() => useTabs());
    const firstId = result.current.activeTabId;
    act(() => result.current.addTab());
    expect(result.current.tabs).toHaveLength(2);
    expect(result.current.activeTabId).not.toBe(firstId);
    expect(result.current.activeTab.id).toBe(result.current.activeTabId);
  });

  it('closeTab on the only remaining tab replaces it with a fresh empty tab', () => {
    const { result } = renderHook(() => useTabs());
    const originalId = result.current.tabs[0].id;
    act(() => result.current.setSign('the-sun'));
    act(() => result.current.closeTab(originalId));
    expect(result.current.tabs).toHaveLength(1);
    expect(result.current.tabs[0].id).not.toBe(originalId);
    expect(result.current.tabs[0].selectedSign).toBe('');
  });

  it('closing the active tab selects the previous tab', () => {
    const { result } = renderHook(() => useTabs());
    const firstId = result.current.tabs[0].id;
    act(() => result.current.addTab());
    const secondId = result.current.activeTabId;
    act(() => result.current.addTab());
    const thirdId = result.current.activeTabId;
    expect(result.current.tabs.map((t) => t.id)).toEqual([firstId, secondId, thirdId]);

    act(() => result.current.closeTab(thirdId));
    expect(result.current.activeTabId).toBe(secondId);
    expect(result.current.tabs.map((t) => t.id)).toEqual([firstId, secondId]);
  });

  it('closing a non-active tab leaves the active tab unchanged', () => {
    const { result } = renderHook(() => useTabs());
    const firstId = result.current.tabs[0].id;
    act(() => result.current.addTab());
    const secondId = result.current.activeTabId;

    act(() => result.current.closeTab(firstId));
    expect(result.current.activeTabId).toBe(secondId);
    expect(result.current.tabs).toHaveLength(1);
  });

  it('selectTab switches the active tab', () => {
    const { result } = renderHook(() => useTabs());
    const firstId = result.current.tabs[0].id;
    act(() => result.current.addTab());
    act(() => result.current.selectTab(firstId));
    expect(result.current.activeTabId).toBe(firstId);
  });
});

describe('per-tab isolation', () => {
  it('setSign on the active tab never touches another tab', () => {
    const { result } = renderHook(() => useTabs());
    const firstId = result.current.tabs[0].id;
    act(() => result.current.addTab());
    const secondId = result.current.activeTabId;

    act(() => result.current.setSign('the-sun'));
    act(() => result.current.selectTab(firstId));
    const first = result.current.tabs.find((t) => t.id === firstId)!;
    const second = result.current.tabs.find((t) => t.id === secondId)!;
    expect(second.selectedSign).toBe('the-sun');
    expect(first.selectedSign).toBe('');
  });
});

describe('rankedHotspots', () => {
  function resultWith(hotspots: ReturnType<typeof makeHotspot>[]): HotspotQueryResult {
    return { facets: { sources: [], interpretants: [] }, hotspots };
  }

  it('sorts by convergence count descending', async () => {
    const low = makeHotspot({ regionId: 'r-low', convergenceCount: 1, matches: [{ interpretant: 'a', kind: 'concept', score: 0.5, exactValue: false, segmentOrdinal: 1 }] });
    const high = makeHotspot({ regionId: 'r-high', convergenceCount: 3, matches: [{ interpretant: 'a', kind: 'concept', score: 0.5, exactValue: false, segmentOrdinal: 1 }] });
    vi.mocked(fetchQuery).mockResolvedValueOnce(resultWith([low, high]));

    const { result } = renderHook(() => useTabs());
    act(() => {
      result.current.setSign('the-sun');
      result.current.setTradition('rider-waite');
    });
    await act(async () => {
      await result.current.runQuery();
    });

    expect(result.current.rankedHotspots.map((h) => h.regionId)).toEqual(['r-high', 'r-low']);
  });

  it('breaks ties by the active-interpretant-scoped score, else overall max', async () => {
    const a = makeHotspot({
      regionId: 'r-a',
      convergenceCount: 2,
      matches: [
        { interpretant: 'sun', kind: 'concept', score: 0.4, exactValue: false, segmentOrdinal: 1 },
        { interpretant: 'moon', kind: 'concept', score: 0.9, exactValue: false, segmentOrdinal: 2 },
      ],
    });
    const b = makeHotspot({
      regionId: 'r-b',
      convergenceCount: 2,
      matches: [
        { interpretant: 'sun', kind: 'concept', score: 0.7, exactValue: false, segmentOrdinal: 1 },
        { interpretant: 'moon', kind: 'concept', score: 0.3, exactValue: false, segmentOrdinal: 2 },
      ],
    });
    vi.mocked(fetchQuery).mockResolvedValueOnce(resultWith([a, b]));

    const { result } = renderHook(() => useTabs());
    act(() => {
      result.current.setSign('the-sun');
      result.current.setTradition('rider-waite');
    });
    await act(async () => {
      await result.current.runQuery();
    });

    // No active interpretant: overall max wins -> a (0.9) before b (0.7)
    expect(result.current.rankedHotspots.map((h) => h.regionId)).toEqual(['r-a', 'r-b']);

    act(() => result.current.setInterpretant('sun'));
    // Scoped to "sun": b (0.7) before a (0.4)
    expect(result.current.rankedHotspots.map((h) => h.regionId)).toEqual(['r-b', 'r-a']);
  });

  it('AND-filters by selected source and interpretant', async () => {
    const matchingBoth = makeHotspot({
      regionId: 'match',
      source: { ...makeHotspot().source, id: 'src-a' },
      matches: [{ interpretant: 'sun', kind: 'concept', score: 0.5, exactValue: false, segmentOrdinal: 1 }],
    });
    const wrongSource = makeHotspot({
      regionId: 'wrong-source',
      source: { ...makeHotspot().source, id: 'src-b' },
      matches: [{ interpretant: 'sun', kind: 'concept', score: 0.5, exactValue: false, segmentOrdinal: 1 }],
    });
    const wrongInterpretant = makeHotspot({
      regionId: 'wrong-interpretant',
      source: { ...makeHotspot().source, id: 'src-a' },
      matches: [{ interpretant: 'moon', kind: 'concept', score: 0.5, exactValue: false, segmentOrdinal: 1 }],
    });
    vi.mocked(fetchQuery).mockResolvedValueOnce(resultWith([matchingBoth, wrongSource, wrongInterpretant]));

    const { result } = renderHook(() => useTabs());
    act(() => {
      result.current.setSign('the-sun');
      result.current.setTradition('rider-waite');
    });
    await act(async () => {
      await result.current.runQuery();
    });

    act(() => {
      result.current.setSourceId('src-a');
      result.current.setInterpretant('sun');
    });

    expect(result.current.rankedHotspots.map((h) => h.regionId)).toEqual(['match']);
  });
});

describe('facet options', () => {
  it('scopes source counts to the interpretant selection, never its own', async () => {
    const srcA = makeHotspot({
      regionId: 'r1',
      source: { ...makeHotspot().source, id: 'src-a', title: 'Source A' },
      matches: [{ interpretant: 'sun', kind: 'concept', score: 0.5, exactValue: false, segmentOrdinal: 1 }],
    });
    const srcB = makeHotspot({
      regionId: 'r2',
      source: { ...makeHotspot().source, id: 'src-b', title: 'Source B' },
      matches: [{ interpretant: 'moon', kind: 'concept', score: 0.5, exactValue: false, segmentOrdinal: 1 }],
    });
    vi.mocked(fetchQuery).mockResolvedValueOnce({ facets: { sources: [], interpretants: [] }, hotspots: [srcA, srcB] });

    const { result } = renderHook(() => useTabs());
    act(() => {
      result.current.setSign('the-sun');
      result.current.setTradition('rider-waite');
    });
    await act(async () => {
      await result.current.runQuery();
    });

    expect(result.current.sourceFacetOptions.options.map((o) => o.id).sort()).toEqual(['src-a', 'src-b']);
    expect(result.current.sourceFacetOptions.allCount).toBe(2);

    act(() => result.current.setInterpretant('sun'));
    expect(result.current.sourceFacetOptions.options.map((o) => o.id)).toEqual(['src-a']);
    expect(result.current.sourceFacetOptions.allCount).toBe(1);
  });

  it('narrows interpretant options by search text without changing counts', async () => {
    const hotspot = makeHotspot({
      regionId: 'r1',
      matches: [
        { interpretant: 'sun', kind: 'concept', score: 0.5, exactValue: false, segmentOrdinal: 1 },
        { interpretant: 'moon', kind: 'concept', score: 0.5, exactValue: false, segmentOrdinal: 1 },
      ],
    });
    vi.mocked(fetchQuery).mockResolvedValueOnce({ facets: { sources: [], interpretants: [] }, hotspots: [hotspot] });

    const { result } = renderHook(() => useTabs());
    act(() => {
      result.current.setSign('the-sun');
      result.current.setTradition('rider-waite');
    });
    await act(async () => {
      await result.current.runQuery();
    });

    expect(result.current.interpretantFacetOptions.options.map((o) => o.id).sort()).toEqual(['moon', 'sun']);

    act(() => result.current.setInterpretantSearch('su'));
    expect(result.current.interpretantFacetOptions.options.map((o) => o.id)).toEqual(['sun']);
    // allCount reflects the source-scoped hotspot count, unaffected by the search text
    expect(result.current.interpretantFacetOptions.allCount).toBe(1);
  });
});

describe('runQuery', () => {
  it('populates queryResult and selects the first hotspot on success', async () => {
    const hotspot = makeHotspot({ regionId: 'r1' });
    vi.mocked(fetchQuery).mockResolvedValueOnce({ facets: { sources: [], interpretants: [] }, hotspots: [hotspot] });

    const { result } = renderHook(() => useTabs());
    act(() => {
      result.current.setSign('the-sun');
      result.current.setTradition('rider-waite');
    });
    await act(async () => {
      await result.current.runQuery();
    });

    expect(result.current.activeTab.queryResult?.hotspots).toHaveLength(1);
    expect(result.current.activeTab.selectedRegionId).toBe('r1');
    expect(result.current.activeTab.isQuerying).toBe(false);
    expect(result.current.activeTab.queryError).toBeNull();
  });

  it('sets queryError and clears the result on failure', async () => {
    vi.mocked(fetchQuery).mockRejectedValueOnce(new Error('sign not found'));

    const { result } = renderHook(() => useTabs());
    act(() => {
      result.current.setSign('missing');
      result.current.setTradition('rider-waite');
    });
    await act(async () => {
      await result.current.runQuery();
    });

    expect(result.current.activeTab.queryResult).toBeNull();
    expect(result.current.activeTab.selectedRegionId).toBeNull();
    expect(result.current.activeTab.queryError).toBe('sign not found');
    expect(result.current.activeTab.isQuerying).toBe(false);
  });
});

describe('sendAgentMessage', () => {
  it('appends a user item then an AI reply on success', async () => {
    vi.mocked(postAgentTurn).mockResolvedValueOnce({
      context: {
        semioticSystem: null,
        sign: null,
        tradition: null,
        sourceId: null,
        interpretant: null,
        minScore: null,
        regionId: null,
        locator: null,
      },
      replyText: 'The sun signifies vitality.',
      instructions: [],
      threadReset: false,
    });

    const { result } = renderHook(() => useTabs());
    await act(async () => {
      await result.current.sendAgentMessage('What does the sun mean?');
    });

    expect(result.current.activeTab.agentItems).toHaveLength(2);
    expect(result.current.activeTab.agentItems[0]).toMatchObject({ kind: 'user', text: 'What does the sun mean?' });
    expect(result.current.activeTab.agentItems[1]).toMatchObject({ kind: 'ai', text: 'The sun signifies vitality.' });
    expect(result.current.activeTab.agentSending).toBe(false);
  });

  it('appends an error item on rejection', async () => {
    vi.mocked(postAgentTurn).mockRejectedValueOnce(new Error('agent unavailable'));

    const { result } = renderHook(() => useTabs());
    await act(async () => {
      await result.current.sendAgentMessage('hello');
    });

    expect(result.current.activeTab.agentItems.at(-1)).toMatchObject({ kind: 'error', text: 'agent unavailable' });
    expect(result.current.activeTab.agentSending).toBe(false);
  });

  it('ignores empty or whitespace-only messages', async () => {
    const { result } = renderHook(() => useTabs());
    await act(async () => {
      await result.current.sendAgentMessage('   ');
    });
    expect(result.current.activeTab.agentItems).toHaveLength(0);
    expect(postAgentTurn).not.toHaveBeenCalled();
  });

  it('replaces the thread with a reset divider when threadReset is true', async () => {
    vi.mocked(postAgentTurn).mockResolvedValueOnce({
      context: {
        semioticSystem: null,
        sign: null,
        tradition: null,
        sourceId: null,
        interpretant: null,
        minScore: null,
        regionId: null,
        locator: null,
      },
      replyText: 'Starting fresh.',
      instructions: [],
      threadReset: true,
    });

    const { result } = renderHook(() => useTabs());
    await act(async () => {
      await result.current.sendAgentMessage('new topic');
    });

    const items = result.current.activeTab.agentItems;
    expect(items).toHaveLength(3);
    expect(items[0].kind).toBe('reset');
    expect(items[1]).toMatchObject({ kind: 'user', text: 'new topic' });
    expect(items[2]).toMatchObject({ kind: 'ai', text: 'Starting fresh.' });
  });

  it('does not send a second message while one is in flight', async () => {
    let resolveFirst!: (value: Awaited<ReturnType<typeof postAgentTurn>>) => void;
    vi.mocked(postAgentTurn).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveFirst = resolve;
      }),
    );

    const { result } = renderHook(() => useTabs());
    let firstSend!: Promise<void>;
    act(() => {
      firstSend = result.current.sendAgentMessage('first');
    });
    await waitFor(() => expect(result.current.activeTab.agentSending).toBe(true));

    await act(async () => {
      await result.current.sendAgentMessage('second');
    });
    expect(postAgentTurn).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveFirst({
        context: {
          semioticSystem: null,
          sign: null,
          tradition: null,
          sourceId: null,
          interpretant: null,
          minScore: null,
          regionId: null,
          locator: null,
        },
        replyText: 'ok',
        instructions: [],
        threadReset: false,
      });
      await firstSend;
    });
  });
});

describe('clearAgentThread', () => {
  it('empties agentItems and rotates the session id', async () => {
    vi.mocked(postAgentTurn).mockResolvedValueOnce({
      context: {
        semioticSystem: null,
        sign: null,
        tradition: null,
        sourceId: null,
        interpretant: null,
        minScore: null,
        regionId: null,
        locator: null,
      },
      replyText: 'hi',
      instructions: [],
      threadReset: false,
    });

    const { result } = renderHook(() => useTabs());
    const originalSessionId = result.current.activeTab.agentSessionId;
    await act(async () => {
      await result.current.sendAgentMessage('hello');
    });
    expect(result.current.activeTab.agentItems).toHaveLength(2);

    act(() => result.current.clearAgentThread());
    expect(result.current.activeTab.agentItems).toHaveLength(0);
    expect(result.current.activeTab.agentSessionId).not.toBe(originalSessionId);
  });
});

describe('agent instructions', () => {
  const CAPABILITIES: AgentCapabilities = {
    commands: [],
    bindings: {
      confirm_query: null,
      confirm_discovery: null,
      execute_query: { method: 'QUERY', path: '/api/query/adhoc', body: 'payload', result: 'regions' },
    },
  };

  const EMPTY_CONTEXT = {
    semioticSystem: null,
    sign: null,
    tradition: null,
    sourceId: null,
    interpretant: null,
    minScore: null,
    regionId: null,
    locator: null,
  };

  function turnWith(instructions: AgentInstruction[]) {
    return { context: EMPTY_CONTEXT, replyText: 'ok', instructions, threadReset: false };
  }

  const EXECUTE_QUERY: AgentInstruction = { type: 'execute_query', payload: { terms: [{ value: 'laughter' }] } };

  it('loads a regions result into the tab the turn was sent from, after a tab switch', async () => {
    const hotspot = makeHotspot({ regionId: 'waite::9-9' });
    vi.mocked(postAgentTurn).mockResolvedValueOnce(turnWith([EXECUTE_QUERY]));
    vi.mocked(fetchBoundRegions).mockResolvedValueOnce({
      facets: { sources: [], interpretants: [] },
      hotspots: [hotspot],
    });

    const { result } = renderHook(() => useTabs(CAPABILITIES));
    const originTabId = result.current.activeTabId;
    let send!: Promise<void>;
    act(() => {
      send = result.current.sendAgentMessage('/query-confirm 7f3a1c9e');
    });
    act(() => result.current.addTab());
    await act(async () => {
      await send;
    });

    const originTab = result.current.tabs.find((tab) => tab.id === originTabId)!;
    expect(originTab.queryResult?.hotspots).toEqual([hotspot]);
    expect(originTab.selectedRegionId).toBe('waite::9-9');
    expect(result.current.activeTab.id).not.toBe(originTabId);
    expect(result.current.activeTab.queryResult).toBeNull();
  });

  it('empties the query form so nothing in it appears to describe the ad-hoc result', async () => {
    vi.mocked(postAgentTurn).mockResolvedValueOnce(turnWith([EXECUTE_QUERY]));
    vi.mocked(fetchBoundRegions).mockResolvedValueOnce({
      facets: { sources: [], interpretants: [] },
      hotspots: [makeHotspot()],
    });

    const { result } = renderHook(() => useTabs(CAPABILITIES));
    act(() => {
      result.current.setSystem('tarot');
      result.current.setSign('the-sun');
      result.current.setTradition('rider-waite');
      result.current.setMinScore(0.9);
    });
    await act(async () => {
      await result.current.sendAgentMessage('/query-confirm 7f3a1c9e');
    });

    expect(result.current.activeTab.selectedSystem).toBe('');
    expect(result.current.activeTab.selectedSign).toBe('');
    expect(result.current.activeTab.selectedTradition).toBe('');
    expect(result.current.activeTab.minScore).toBeNull();
    expect(result.current.activeTab.queryResult).not.toBeNull();
  });

  it('appends an error and leaves the existing result untouched when a type is undeclared', async () => {
    vi.mocked(fetchQuery).mockResolvedValueOnce({
      facets: { sources: [], interpretants: [] },
      hotspots: [makeHotspot({ regionId: 'waite::1-1' })],
    });
    vi.mocked(postAgentTurn).mockResolvedValueOnce(turnWith([{ type: 'render_chart', payload: {} }]));

    const { result } = renderHook(() => useTabs(CAPABILITIES));
    await act(async () => {
      await result.current.runQuery();
    });
    await act(async () => {
      await result.current.sendAgentMessage('do something');
    });

    expect(result.current.activeTab.agentItems.at(-1)).toMatchObject({ kind: 'error' });
    expect(result.current.activeTab.queryResult?.hotspots[0].regionId).toBe('waite::1-1');
    expect(fetchBoundRegions).not.toHaveBeenCalled();
  });

  it('runs nothing for a confirm_query instruction — its affordance sends a command instead', async () => {
    vi.mocked(postAgentTurn).mockResolvedValueOnce(
      turnWith([{ type: 'confirm_query', payload: { confirm_command: '/query-confirm 7f3a1c9e' } }]),
    );

    const { result } = renderHook(() => useTabs(CAPABILITIES));
    await act(async () => {
      await result.current.sendAgentMessage('/query laughter');
    });

    expect(fetchBoundRegions).not.toHaveBeenCalled();
    expect(result.current.activeTab.agentItems.at(-1)).toMatchObject({ kind: 'ai' });
  });

  it('runs nothing for a confirm_discovery instruction, and reports no error', async () => {
    // Declared with a null binding, so it is known-but-unexecutable rather
    // than undeclared (FR-CAP-13, FR-DS-31) — the difference between the panel
    // rendering a chip and an error bubble appearing beside the plan.
    vi.mocked(postAgentTurn).mockResolvedValueOnce(
      turnWith([{ type: 'confirm_discovery', payload: { confirm_command: '/discover-confirm 7f3a1c' } }]),
    );

    const { result } = renderHook(() => useTabs(CAPABILITIES));
    await act(async () => {
      await result.current.sendAgentMessage('/discover "where joy is", laughter');
    });

    expect(fetchBoundRegions).not.toHaveBeenCalled();
    expect(result.current.activeTab.agentItems.at(-1)).toMatchObject({ kind: 'ai' });
  });
});
