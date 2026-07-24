import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ComponentProps } from 'react';
import { HotspotDetailPanel } from './HotspotDetailPanel';
import { fetchSegments } from '../api/client';
import { makeHotspot, makeSegment } from '../test/fixtures';

vi.mock('../api/client', () => ({
  fetchSegments: vi.fn(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

function baseProps(overrides: Partial<ComponentProps<typeof HotspotDetailPanel>> = {}): ComponentProps<typeof HotspotDetailPanel> {
  return {
    hotspot: makeHotspot(),
    hasResult: true,
    activeInterpretant: null,
    onPrev: vi.fn(),
    onNext: vi.fn(),
    canGoPrev: false,
    canGoNext: false,
    ...overrides,
  };
}

describe('empty states', () => {
  it('renders nothing but an empty aside when there is no hotspot and no result', () => {
    render(<HotspotDetailPanel {...baseProps({ hotspot: null, hasResult: false })} />);
    expect(screen.queryByText('Nothing selected yet')).not.toBeInTheDocument();
  });

  it('shows "Nothing selected yet" when there is a result but no hotspot selected', () => {
    render(<HotspotDetailPanel {...baseProps({ hotspot: null, hasResult: true })} />);
    expect(screen.getByText('Nothing selected yet')).toBeInTheDocument();
  });
});

describe('rendered hotspot', () => {
  it('renders title, convergence badge, and segment text', () => {
    const hotspot = makeHotspot({
      locator: 'Ecclesiasticus 43:1',
      convergenceCount: 1,
      segments: [makeSegment({ ordinal: 1, text: 'The pride of the height.' })],
    });
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    expect(screen.getByRole('heading', { name: 'Ecclesiasticus 43:1' })).toBeInTheDocument();
    expect(screen.getByText('The pride of the height.')).toBeInTheDocument();
  });

  it('renders one chip per match and highlights the clicked one as anchored', async () => {
    const hotspot = makeHotspot({
      segments: [makeSegment({ ordinal: 1 }), makeSegment({ ordinal: 2, text: 'second segment' })],
      matches: [
        { interpretant: 'sun', kind: 'concept', score: 0.8, exactValue: false, segmentOrdinal: 1 },
        { interpretant: 'moon', kind: 'concept', score: 0.6, exactValue: false, segmentOrdinal: 2 },
      ],
    });
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    const chip = screen.getByText('moon · 0.60');
    await userEvent.click(chip);
    expect(chip).toHaveClass('anchored');
  });

  it('dims non-active-interpretant chips and shows the dimmed note', () => {
    const hotspot = makeHotspot({
      matches: [
        { interpretant: 'sun', kind: 'concept', score: 0.8, exactValue: false, segmentOrdinal: 1 },
        { interpretant: 'moon', kind: 'concept', score: 0.6, exactValue: false, segmentOrdinal: 1 },
      ],
    });
    render(<HotspotDetailPanel {...baseProps({ hotspot, activeInterpretant: 'sun' })} />);
    expect(screen.getByText('sun · 0.80')).toHaveClass('active');
    expect(screen.getByText('moon · 0.60')).toHaveClass('dimmed');
    expect(screen.getByText('(dimmed = matched but outside current filter)')).toBeInTheDocument();
  });

  it('prev/next buttons respect canGoPrev/canGoNext and call their callbacks', async () => {
    const onPrev = vi.fn();
    const onNext = vi.fn();
    render(<HotspotDetailPanel {...baseProps({ onPrev, onNext, canGoPrev: true, canGoNext: false })} />);
    expect(screen.getByLabelText('Previous hotspot')).toBeEnabled();
    expect(screen.getByLabelText('Next hotspot')).toBeDisabled();
    await userEvent.click(screen.getByLabelText('Previous hotspot'));
    expect(onPrev).toHaveBeenCalledTimes(1);
  });

  it('copies the citation reference and shows transient "Copied" state', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const hotspot = makeHotspot({ locator: 'Ecclesiasticus 43:1', source: { ...makeHotspot().source, citation_label: 'Eccl.' } });
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    // userEvent.setup() installs its own harmless clipboard stub over jsdom
    // (which has no real Clipboard API) — spy on it rather than pre-mocking
    // navigator.clipboard, which setup() would silently replace anyway.
    const writeTextSpy = vi.spyOn(navigator.clipboard, 'writeText');
    await user.click(screen.getByText('Copy reference'));
    expect(writeTextSpy).toHaveBeenCalledWith('Eccl. — Ecclesiasticus 43:1');
    expect(screen.getByText('Copied')).toBeInTheDocument();
    vi.advanceTimersByTime(1300);
    await waitFor(() => expect(screen.getByText('Copy reference')).toBeInTheDocument());
    vi.useRealTimers();
  });
});

describe('Add Context', () => {
  it('gap-fills first: when segments have a gap, requests the full min..max range', async () => {
    const hotspot = makeHotspot({
      segments: [makeSegment({ ordinal: 1 }), makeSegment({ ordinal: 4, text: 'later segment' })],
      matches: [{ interpretant: 'sun', kind: 'concept', score: 0.8, exactValue: false, segmentOrdinal: 1 }],
    });
    vi.mocked(fetchSegments).mockResolvedValueOnce([
      makeSegment({ ordinal: 2, text: 'gap 2' }),
      makeSegment({ ordinal: 3, text: 'gap 3' }),
    ]);
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    await userEvent.click(screen.getByText('+ Add Context'));
    await waitFor(() => expect(fetchSegments).toHaveBeenCalledWith(hotspot.source.id, 1, 4));
    expect(await screen.findByText('gap 2')).toBeInTheDocument();
    expect(screen.getByText('gap 3')).toBeInTheDocument();
  });

  it('with no gap, probes one segment before the leading edge and one after the trailing edge', async () => {
    const hotspot = makeHotspot({
      segments: [makeSegment({ ordinal: 5, section: '43', text: 'middle' })],
    });
    vi.mocked(fetchSegments).mockImplementation((_sourceId, start, end) => {
      if (start === 4 && end === 4) return Promise.resolve([makeSegment({ ordinal: 4, section: '43', text: 'before' })]);
      if (start === 6 && end === 6) return Promise.resolve([makeSegment({ ordinal: 6, section: '43', text: 'after' })]);
      return Promise.resolve([]);
    });
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    await userEvent.click(screen.getByText('+ Add Context'));
    expect(await screen.findByText('before')).toBeInTheDocument();
    expect(await screen.findByText('after')).toBeInTheDocument();
  });

  it('stops the leading edge at a chapter/section boundary', async () => {
    const hotspot = makeHotspot({
      segments: [makeSegment({ ordinal: 5, section: '43', text: 'middle' })],
    });
    vi.mocked(fetchSegments).mockImplementation((_sourceId, start, end) => {
      if (start === 4 && end === 4) return Promise.resolve([makeSegment({ ordinal: 4, section: '42', text: 'other chapter' })]);
      return Promise.resolve([]);
    });
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    await userEvent.click(screen.getByText('+ Add Context'));
    await waitFor(() => expect(fetchSegments).toHaveBeenCalled());
    expect(screen.queryByText('other chapter')).not.toBeInTheDocument();
  });

  it('stops an edge at the source start/end when the probe returns nothing', async () => {
    const hotspot = makeHotspot({
      segments: [makeSegment({ ordinal: 5, section: '43', text: 'middle' })],
    });
    vi.mocked(fetchSegments).mockResolvedValue([]);
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    const button = screen.getByText('+ Add Context');
    await userEvent.click(button);
    await waitFor(() => expect(fetchSegments).toHaveBeenCalledTimes(2));
    // Both edges now bounded with no gap -> button reflects fully loaded state
    await waitFor(() => expect(screen.getByText('Full context loaded')).toBeInTheDocument());
    expect(screen.getByText('Full context loaded').closest('button')).toBeDisabled();
  });

  it('shows a distinct error and leaves the hotspot displayed when the context request fails', async () => {
    const hotspot = makeHotspot({
      segments: [makeSegment({ ordinal: 5, section: '43', text: 'middle' })],
    });
    vi.mocked(fetchSegments).mockRejectedValue(new Error('segments unavailable'));
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    await userEvent.click(screen.getByText('+ Add Context'));
    expect(await screen.findByText('segments unavailable')).toBeInTheDocument();
    expect(screen.getByText('middle')).toBeInTheDocument();
  });
});
