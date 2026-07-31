// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import type { ComponentProps } from 'react';
import { HotspotDetailPanel } from './HotspotDetailPanel';
import { extendContext } from '../api/client';
import type { ExtendedRegionRef, Hotspot } from '../api/types';
import { makeExtendedRegion, makeHotspot, makeSegment, makeSource } from '../test/fixtures';

vi.mock('../api/client', () => ({
  extendContext: vi.fn(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

function baseProps(overrides: Partial<ComponentProps<typeof HotspotDetailPanel>> = {}): ComponentProps<typeof HotspotDetailPanel> {
  return {
    hotspot: makeHotspot(),
    hasResult: true,
    augmentation: null,
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

  it('still shows each segment\'s own locator even when it repeats the hotspot\'s own (a chapter-only source with nothing finer to cite)', () => {
    const chapterTitle = '14. CHAPTER XIV The Author';
    const hotspot = makeHotspot({
      locator: chapterTitle,
      segments: [
        makeSegment({ ordinal: 1, locator: chapterTitle, text: 'first' }),
        makeSegment({ ordinal: 2, locator: chapterTitle, text: 'second' }),
        makeSegment({ ordinal: 3, locator: chapterTitle, text: 'third' }),
      ],
    });
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    // The panel heading states it once, plus once per segment — never omitted.
    expect(screen.getAllByText(chapterTitle)).toHaveLength(4);
    expect(document.querySelectorAll('.segment-locator')).toHaveLength(3);
  });

  it('shows each segment\'s own locator when it names something finer than the hotspot\'s own (e.g. a verse within a region)', () => {
    const hotspot = makeHotspot({
      locator: 'Genesis 21:5–8',
      segments: [
        makeSegment({ ordinal: 1, locator: 'Genesis 21:5', text: 'first' }),
        makeSegment({ ordinal: 2, locator: 'Genesis 21:8', text: 'second' }),
      ],
    });
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    expect(screen.getByText('Genesis 21:5')).toBeInTheDocument();
    expect(screen.getByText('Genesis 21:8')).toBeInTheDocument();
  });

  it('renders a gap marker across a non-adjacent ordinal jump, alongside each segment\'s own (repeated) locator', () => {
    const chapterTitle = '17. Fishes, Insects, Animals, Reptiles and Birds';
    const hotspot = makeHotspot({
      locator: chapterTitle,
      segments: [
        makeSegment({ ordinal: 1, locator: chapterTitle, text: 'first' }),
        makeSegment({ ordinal: 2, locator: chapterTitle, text: 'second' }),
        makeSegment({ ordinal: 10, locator: chapterTitle, text: 'far later' }),
      ],
    });
    // Both edges confirmed bounded so only the internal ordinal gap is under test here.
    const initialExtendedRegion = { regionId: hotspot.regionId, locator: chapterTitle, segments: hotspot.segments, leadingBounded: true, trailingBounded: true };
    render(<HotspotDetailPanel {...baseProps({ hotspot, initialExtendedRegion })} />);
    expect(document.querySelectorAll('.segment-locator')).toHaveLength(3);
    expect(document.querySelectorAll('.segment-gap')).toHaveLength(1);
  });

  it('shows leading and trailing gap markers for a chapter_section source when neither edge is confirmed bounded (the default, unconfirmed state before "Add Context")', () => {
    const chapterTitle = '17. Fishes, Insects, Animals, Reptiles and Birds';
    const hotspot = makeHotspot({
      locator: chapterTitle,
      source: makeSource({ structure_scheme: 'chapter_section' }),
      segments: [
        makeSegment({ ordinal: 4, locator: chapterTitle, text: 'first' }),
        makeSegment({ ordinal: 5, locator: chapterTitle, text: 'second' }),
      ],
    });
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    // No internal gap (ordinals are adjacent), so both markers shown are the edges.
    expect(document.querySelectorAll('.segment-gap')).toHaveLength(2);
  });

  it.each(['scripture_verse', 'numbered_section'])(
    'never shows leading/trailing gap markers for a %s source (a verse or numbered-section range like the Bible or the Bahir), even when unbounded',
    (structureScheme) => {
      const hotspot = makeHotspot({
        locator: 'Genesis 3:7–15',
        source: makeSource({ structure_scheme: structureScheme }),
        segments: [
          makeSegment({ ordinal: 1, locator: 'Genesis 3:7', text: 'first' }),
          makeSegment({ ordinal: 8, locator: 'Genesis 3:15', text: 'second' }),
        ],
      });
      render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
      // The ordinal jump between the two segments is still a real internal gap.
      expect(document.querySelectorAll('.segment-gap')).toHaveLength(1);
    },
  );

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

  it('renders every matched chip uniformly regardless of the active facet filter', () => {
    const hotspot = makeHotspot({
      matches: [
        { interpretant: 'sun', kind: 'concept', score: 0.8, exactValue: false, segmentOrdinal: 1 },
        { interpretant: 'moon', kind: 'concept', score: 0.6, exactValue: false, segmentOrdinal: 1 },
      ],
    });
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    expect(screen.getByText('sun · 0.80')).toHaveClass('interpretant-chip');
    expect(screen.getByText('moon · 0.60')).toHaveClass('interpretant-chip');
    expect(screen.queryByText('(dimmed = matched but outside current filter)')).not.toBeInTheDocument();
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
  it('calls extendContext with the current segment range and renders the grown window', async () => {
    const hotspot = makeHotspot({
      segments: [makeSegment({ ordinal: 5, section: '43', text: 'middle' })],
    });
    vi.mocked(extendContext).mockResolvedValueOnce(
      makeExtendedRegion({
        segments: [
          makeSegment({ ordinal: 4, section: '43', text: 'before' }),
          makeSegment({ ordinal: 5, section: '43', text: 'middle' }),
          makeSegment({ ordinal: 6, section: '43', text: 'after' }),
        ],
        leadingBounded: false,
        trailingBounded: false,
      }),
    );
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    await userEvent.click(screen.getByText('+ Add Context'));
    await waitFor(() => expect(extendContext).toHaveBeenCalledWith(hotspot.source.id, 5, 5, 1));
    expect(await screen.findByText('before')).toBeInTheDocument();
    expect(screen.getByText('after')).toBeInTheDocument();
  });

  it('passes the current segment count so the backend can fill a gap first instead of also growing edges', async () => {
    // A hotspot's own `segments` can be sparse (match-carrying ordinals
    // only) — here ordinals 1 and 4 with 2 and 3 missing. `loadedCount` (2)
    // tells the backend there's a gap in [1, 4], so it fills only that,
    // deferring edge growth to the next activation (FR-CE-02/03).
    const hotspot = makeHotspot({
      segments: [makeSegment({ ordinal: 1, text: 'one' }), makeSegment({ ordinal: 4, text: 'four' })],
    });
    vi.mocked(extendContext).mockResolvedValueOnce(
      makeExtendedRegion({
        segments: [
          makeSegment({ ordinal: 1, text: 'one' }),
          makeSegment({ ordinal: 2, text: 'gap two' }),
          makeSegment({ ordinal: 3, text: 'gap three' }),
          makeSegment({ ordinal: 4, text: 'four' }),
        ],
        leadingBounded: false,
        trailingBounded: false,
      }),
    );
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    await userEvent.click(screen.getByText('+ Add Context'));
    await waitFor(() => expect(extendContext).toHaveBeenCalledWith(hotspot.source.id, 1, 4, 2));
    expect(await screen.findByText('gap two')).toBeInTheDocument();
    expect(screen.getByText('gap three')).toBeInTheDocument();
  });

  it('reports the widened region to the parent when the window grew', async () => {
    const hotspot = makeHotspot({ regionId: 'region-1', segments: [makeSegment({ ordinal: 5, text: 'middle' })] });
    const onContextExtended = vi.fn();
    vi.mocked(extendContext).mockResolvedValueOnce(
      makeExtendedRegion({
        regionId: 'region-1-extended',
        locator: 'Ecclesiasticus 43:1-2',
        segments: [
          makeSegment({ ordinal: 4, text: 'before' }),
          makeSegment({ ordinal: 5, text: 'middle' }),
          makeSegment({ ordinal: 6, text: 'after' }),
        ],
      }),
    );
    render(<HotspotDetailPanel {...baseProps({ hotspot, onContextExtended })} />);
    await userEvent.click(screen.getByText('+ Add Context'));
    await waitFor(() =>
      expect(onContextExtended).toHaveBeenCalledWith(
        expect.objectContaining({
          regionId: 'region-1-extended',
          locator: 'Ecclesiasticus 43:1-2',
        }),
      ),
    );
    expect(screen.getByText('- Clear Context')).toBeInTheDocument();
  });

  it('regression: shows "Clear Context" even when a gap-fill-only response keeps the same region_id', async () => {
    // The exact bug this test locks in: `region_id` encodes only the
    // window's min/max ordinals, so a gap-fill (which adds segments inside
    // the range without moving either end) never changes it. Detecting
    // "did anything grow" by comparing `region_id` would wrongly treat this
    // as a no-op — segment count against the hotspot's own original segments
    // is the correct test.
    const hotspot = makeHotspot({
      regionId: 'region-1',
      segments: [makeSegment({ ordinal: 1, text: 'one' }), makeSegment({ ordinal: 4, text: 'four' })],
    });
    const onContextExtended = vi.fn();
    vi.mocked(extendContext).mockResolvedValueOnce(
      makeExtendedRegion({
        regionId: 'region-1', // unchanged — gap-fill never moves the min/max ordinal
        segments: [
          makeSegment({ ordinal: 1, text: 'one' }),
          makeSegment({ ordinal: 2, text: 'gap two' }),
          makeSegment({ ordinal: 3, text: 'gap three' }),
          makeSegment({ ordinal: 4, text: 'four' }),
        ],
        leadingBounded: false,
        trailingBounded: false,
      }),
    );
    render(<HotspotDetailPanel {...baseProps({ hotspot, onContextExtended })} />);
    await userEvent.click(screen.getByText('+ Add Context'));

    expect(await screen.findByText('gap two')).toBeInTheDocument();
    expect(screen.getByText('- Clear Context')).toBeInTheDocument();
    await waitFor(() => expect(onContextExtended).toHaveBeenCalledWith(expect.objectContaining({ regionId: 'region-1' })));
    expect(onContextExtended).not.toHaveBeenCalledWith(null);
  });

  it('reports no widened region when nothing grew (both edges already bounded)', async () => {
    const hotspot = makeHotspot({ regionId: 'region-1', segments: [makeSegment({ ordinal: 5, text: 'middle' })] });
    const onContextExtended = vi.fn();
    vi.mocked(extendContext).mockResolvedValueOnce(
      makeExtendedRegion({
        regionId: 'region-1',
        locator: hotspot.locator,
        segments: hotspot.segments,
        leadingBounded: true,
        trailingBounded: true,
      }),
    );
    render(<HotspotDetailPanel {...baseProps({ hotspot, onContextExtended })} />);
    await userEvent.click(screen.getByText('+ Add Context'));
    await waitFor(() => expect(onContextExtended).toHaveBeenCalledWith(null));
  });

  it('shows "Full context loaded" and disables the button once both edges are bounded', async () => {
    const hotspot = makeHotspot({
      segments: [makeSegment({ ordinal: 5, section: '43', text: 'middle' })],
    });
    vi.mocked(extendContext).mockResolvedValueOnce(
      makeExtendedRegion({ segments: hotspot.segments, leadingBounded: true, trailingBounded: true }),
    );
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    await userEvent.click(screen.getByText('+ Add Context'));
    await waitFor(() => expect(screen.getByText('Full context loaded')).toBeInTheDocument());
    expect(screen.getByText('Full context loaded').closest('button')).toBeDisabled();
  });

  it('stays extendable when only one edge is still bounded', async () => {
    const hotspot = makeHotspot({
      segments: [makeSegment({ ordinal: 5, section: '43', text: 'middle' })],
    });
    vi.mocked(extendContext).mockResolvedValueOnce(
      makeExtendedRegion({
        segments: [
          makeSegment({ ordinal: 5, section: '43', text: 'middle' }),
          makeSegment({ ordinal: 6, section: '43', text: 'after' }),
        ],
        leadingBounded: true,
        trailingBounded: false,
      }),
    );
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    await userEvent.click(screen.getByText('+ Add Context'));
    expect(await screen.findByText('after')).toBeInTheDocument();
    expect(screen.getByText('+ Add Context')).toBeInTheDocument();
    expect(screen.queryByText('Full context loaded')).not.toBeInTheDocument();
  });

  it('keeps extending across repeated activations, each call scoped to the currently loaded range', async () => {
    const hotspot = makeHotspot({
      segments: [makeSegment({ ordinal: 50, section: '', text: 'middle' })],
    });
    vi.mocked(extendContext).mockResolvedValueOnce(
      makeExtendedRegion({
        segments: [
          makeSegment({ ordinal: 49, section: '', text: 'before once' }),
          makeSegment({ ordinal: 50, section: '', text: 'middle' }),
          makeSegment({ ordinal: 51, section: '', text: 'after once' }),
        ],
        leadingBounded: false,
        trailingBounded: false,
      }),
    );
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    const button = screen.getByText('+ Add Context');
    await userEvent.click(button);
    expect(await screen.findByText('before once')).toBeInTheDocument();
    expect(screen.getByText('after once')).toBeInTheDocument();
    // Still extendable after the first activation — not prematurely "fully loaded".
    expect(screen.getByText('+ Add Context')).toBeInTheDocument();
    expect(screen.queryByText('Full context loaded')).not.toBeInTheDocument();

    vi.mocked(extendContext).mockResolvedValueOnce(
      makeExtendedRegion({
        segments: [
          makeSegment({ ordinal: 49, section: '', text: 'before once' }),
          makeSegment({ ordinal: 50, section: '', text: 'middle' }),
          makeSegment({ ordinal: 51, section: '', text: 'after once' }),
        ],
        leadingBounded: true,
        trailingBounded: true,
      }),
    );
    await userEvent.click(screen.getByText('+ Add Context'));
    await waitFor(() => expect(extendContext).toHaveBeenLastCalledWith(hotspot.source.id, 49, 51, 3));
    await waitFor(() => expect(screen.getByText('Full context loaded')).toBeInTheDocument());
    expect(screen.getByText('Full context loaded').closest('button')).toBeDisabled();
  });

  it('restores a previously widened context on remount (navigated away and back to this hotspot)', () => {
    const hotspot = makeHotspot({ regionId: 'region-1', segments: [makeSegment({ ordinal: 5, text: 'middle' })] });
    const initialExtendedRegion = {
      regionId: 'region-1-extended',
      locator: 'Ecclesiasticus 43:1-2',
      segments: [
        makeSegment({ ordinal: 4, text: 'before' }),
        makeSegment({ ordinal: 5, text: 'middle' }),
        makeSegment({ ordinal: 6, text: 'after' }),
      ],
      leadingBounded: true,
      trailingBounded: false,
    };
    render(<HotspotDetailPanel {...baseProps({ hotspot, initialExtendedRegion })} />);

    expect(screen.getByText('before')).toBeInTheDocument();
    expect(screen.getByText('after')).toBeInTheDocument();
    expect(extendContext).not.toHaveBeenCalled();
    // Still extendable on the trailing edge — reflects the restored bounded flags.
    expect(screen.getByText('+ Add Context')).toBeInTheDocument();
    expect(screen.getByText('- Clear Context')).toBeInTheDocument();
  });

  it('does not show "Clear Context" when there is no active extension', () => {
    render(<HotspotDetailPanel {...baseProps()} />);
    expect(screen.queryByText('- Clear Context')).not.toBeInTheDocument();
  });

  it('"Clear Context" resets to the hotspot\'s own segments and reports the clear to the parent', async () => {
    const hotspot = makeHotspot({ regionId: 'region-1', segments: [makeSegment({ ordinal: 5, text: 'middle' })] });
    const onContextExtended = vi.fn();
    const initialExtendedRegion = {
      regionId: 'region-1-extended',
      locator: 'Ecclesiasticus 43:1-2',
      segments: [
        makeSegment({ ordinal: 4, text: 'before' }),
        makeSegment({ ordinal: 5, text: 'middle' }),
        makeSegment({ ordinal: 6, text: 'after' }),
      ],
      leadingBounded: false,
      trailingBounded: false,
    };
    render(<HotspotDetailPanel {...baseProps({ hotspot, onContextExtended, initialExtendedRegion })} />);
    expect(screen.getByText('before')).toBeInTheDocument();

    await userEvent.click(screen.getByText('- Clear Context'));

    expect(screen.queryByText('before')).not.toBeInTheDocument();
    expect(screen.queryByText('after')).not.toBeInTheDocument();
    expect(screen.getByText('middle')).toBeInTheDocument();
    expect(screen.queryByText('- Clear Context')).not.toBeInTheDocument();
    expect(onContextExtended).toHaveBeenCalledWith(null);
  });

  it('shows a distinct error and leaves the hotspot displayed when the context request fails', async () => {
    const hotspot = makeHotspot({
      segments: [makeSegment({ ordinal: 5, section: '43', text: 'middle' })],
    });
    vi.mocked(extendContext).mockRejectedValue(new Error('segments unavailable'));
    render(<HotspotDetailPanel {...baseProps({ hotspot })} />);
    await userEvent.click(screen.getByText('+ Add Context'));
    expect(await screen.findByText('segments unavailable')).toBeInTheDocument();
    expect(screen.getByText('middle')).toBeInTheDocument();
  });
});

// A minimal stand-in for the relevant slice of `App.tsx` + `useTabs.ts`:
// a `key` that changes with the selected hotspot (forcing the same
// mount/unmount cycle `App.tsx` relies on) and a *map* of widened contexts
// keyed by hotspot regionId — exactly `Tab.extendedRegions`/
// `activeExtendedRegion`'s real shape in `useTabs.ts` (one entry per
// hotspot, so widening B's context can never clobber A's). Exercises the
// real React reconciliation the isolated component tests above don't: does
// navigating away and back actually remount with the right restored props,
// not just "would the props be correct if passed."
function NavigationHarness({ a, b }: { a: Hotspot; b: Hotspot }) {
  const [selectedId, setSelectedId] = useState(a.regionId);
  const [extendedRegions, setExtendedRegions] = useState<Record<string, NonNullable<ExtendedRegionRef>>>({});
  const hotspot = selectedId === a.regionId ? a : b;
  const activeExtendedRegion = extendedRegions[selectedId] ?? null;
  function setExtendedRegion(region: ExtendedRegionRef) {
    setExtendedRegions((prev) => {
      if (region === null) {
        const { [selectedId]: _removed, ...rest } = prev;
        return rest;
      }
      return { ...prev, [selectedId]: region };
    });
  }
  return (
    <>
      <button type="button" onClick={() => setSelectedId(a.regionId)}>
        select A
      </button>
      <button type="button" onClick={() => setSelectedId(b.regionId)}>
        select B
      </button>
      <HotspotDetailPanel
        key={hotspot.regionId}
        {...baseProps({ hotspot, initialExtendedRegion: activeExtendedRegion, onContextExtended: setExtendedRegion })}
      />
    </>
  );
}

describe('context persists across hotspot navigation (integration, real remount)', () => {
  it('restores the widened segments after navigating to a different hotspot and back', async () => {
    const a = makeHotspot({ regionId: 'r-a', segments: [makeSegment({ ordinal: 5, text: 'middle' })] });
    const b = makeHotspot({ regionId: 'r-b', segments: [makeSegment({ ordinal: 50, text: 'other hotspot' })] });
    vi.mocked(extendContext).mockResolvedValueOnce(
      makeExtendedRegion({
        regionId: 'r-a-extended',
        locator: 'Ecclesiasticus 43:1-2',
        segments: [
          makeSegment({ ordinal: 4, text: 'before' }),
          makeSegment({ ordinal: 5, text: 'middle' }),
          makeSegment({ ordinal: 6, text: 'after' }),
        ],
        leadingBounded: false,
        trailingBounded: false,
      }),
    );

    render(<NavigationHarness a={a} b={b} />);
    await userEvent.click(screen.getByText('+ Add Context'));
    expect(await screen.findByText('before')).toBeInTheDocument();
    expect(screen.getByText('after')).toBeInTheDocument();

    await userEvent.click(screen.getByText('select B'));
    expect(screen.getByText('other hotspot')).toBeInTheDocument();
    expect(screen.queryByText('before')).not.toBeInTheDocument();

    await userEvent.click(screen.getByText('select A'));
    expect(await screen.findByText('before')).toBeInTheDocument();
    expect(screen.getByText('middle')).toBeInTheDocument();
    expect(screen.getByText('after')).toBeInTheDocument();
    expect(screen.getByText('- Clear Context')).toBeInTheDocument();
  });

  it('regression: A -> extend -> B -> extend -> back to A must still show A\'s own widened context', async () => {
    // This is the exact sequence that broke under a single-slot design
    // (`Tab.extendedRegion` as one object, not a map): widening B's context
    // silently overwrote A's already-remembered one.
    const a = makeHotspot({ regionId: 'r-a', segments: [makeSegment({ ordinal: 5, text: 'a-middle' })] });
    const b = makeHotspot({ regionId: 'r-b', segments: [makeSegment({ ordinal: 50, text: 'b-middle' })] });
    vi.mocked(extendContext).mockResolvedValueOnce(
      makeExtendedRegion({
        regionId: 'r-a-extended',
        segments: [
          makeSegment({ ordinal: 4, text: 'a-before' }),
          makeSegment({ ordinal: 5, text: 'a-middle' }),
          makeSegment({ ordinal: 6, text: 'a-after' }),
        ],
      }),
    );

    render(<NavigationHarness a={a} b={b} />);
    await userEvent.click(screen.getByText('+ Add Context'));
    expect(await screen.findByText('a-before')).toBeInTheDocument();

    await userEvent.click(screen.getByText('select B'));
    expect(await screen.findByText('b-middle')).toBeInTheDocument();

    vi.mocked(extendContext).mockResolvedValueOnce(
      makeExtendedRegion({
        regionId: 'r-b-extended',
        segments: [
          makeSegment({ ordinal: 49, text: 'b-before' }),
          makeSegment({ ordinal: 50, text: 'b-middle' }),
          makeSegment({ ordinal: 51, text: 'b-after' }),
        ],
      }),
    );
    await userEvent.click(screen.getByText('+ Add Context'));
    expect(await screen.findByText('b-before')).toBeInTheDocument();

    await userEvent.click(screen.getByText('select A'));
    expect(await screen.findByText('a-before')).toBeInTheDocument();
    expect(screen.getByText('a-after')).toBeInTheDocument();
    expect(screen.getByText('- Clear Context')).toBeInTheDocument();

    await userEvent.click(screen.getByText('select B'));
    expect(await screen.findByText('b-before')).toBeInTheDocument();
    expect(screen.getByText('b-after')).toBeInTheDocument();
  });
});

it('shows no AI analysis block when the region has no augmentation', () => {
  render(<HotspotDetailPanel {...baseProps({ augmentation: null })} />);
  expect(screen.queryByText('AI analysis')).not.toBeInTheDocument();
});

it('shows the augmentation, labelled as generated analysis', () => {
  render(<HotspotDetailPanel {...baseProps({ augmentation: { label: '[R1]', text: 'Sara laughs.' } })} />);
  expect(screen.getByText('AI analysis')).toBeInTheDocument();
  expect(screen.getByText('Sara laughs.')).toBeInTheDocument();
});

it('places the analysis above the verbatim segments so it cannot read as source text', () => {
  const { container } = render(
    <HotspotDetailPanel {...baseProps({ augmentation: { label: '[R1]', text: 'Sara laughs.' } })} />,
  );

  const analysis = container.querySelector('.augmented-section');
  const segments = container.querySelector('.segment-list');
  expect(analysis).not.toBeNull();
  expect(segments).not.toBeNull();
  expect(analysis!.compareDocumentPosition(segments!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

it('renders the augmentation as markdown rather than literal syntax', () => {
  const text = [
    'The passage expresses a mix of emotions:',
    '',
    '1. **Joy**: "God hath made a laughter for me".',
    '2. **Humor**: hints of sarcasm.',
  ].join('\n');

  const { container } = render(<HotspotDetailPanel {...baseProps({ augmentation: { label: '[R1]', text } })} />);

  expect(container.querySelectorAll('.augmented-body li')).toHaveLength(2);
  expect(container.querySelector('.augmented-body strong')?.textContent).toBe('Joy');
  expect(screen.queryByText(/\*\*Joy\*\*/)).not.toBeInTheDocument();
});
