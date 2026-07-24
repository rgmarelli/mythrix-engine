import { useState } from 'react';
import { fetchSegments } from '../api/client';
import type { Hotspot, HotspotSegment } from '../api/types';
import { convergenceLabel, hotspotTitle } from '../utils/hotspot';

interface Props {
  hotspot: Hotspot | null;
  activeInterpretant: string | null;
  onPrev: () => void;
  onNext: () => void;
  canGoPrev: boolean;
  canGoNext: boolean;
  onBack?: () => void;
  open?: boolean;
}

function citationRef(hotspot: Hotspot): string {
  const attribution = hotspot.source.citation_label || `${hotspot.source.title}, ${hotspot.source.author}`;
  return hotspot.locator ? `${attribution} — ${hotspot.locator}` : attribution;
}

function segmentElementId(regionId: string, ordinal: number): string {
  return `segment-${regionId}-${ordinal}`;
}

function sortByOrdinal(segments: HotspotSegment[]): HotspotSegment[] {
  return [...segments].sort((a, b) => a.ordinal - b.ordinal);
}

/** A hotspot's constituent segments rendered individually (never one merged blob), each
 * interpretant chip linking to the specific segment it anchors to (FR17) —
 * clicking a chip scrolls to and highlights that segment — plus an on-demand
 * AI summary over the full loaded context (matched segments plus any
 * gap-filled/expanded via Add Context, `hotspot-context-expansion`) and
 * hotspot navigation. Mounted by `App.tsx` with `key={hotspot.regionId}` so
 * all of this state never leaks from one hotspot to the next. */
export function HotspotDetailPanel({
  hotspot,
  activeInterpretant,
  onPrev,
  onNext,
  canGoPrev,
  canGoNext,
  onBack,
  open,
}: Props) {
  const [activeSegmentOrdinal, setActiveSegmentOrdinal] = useState<number | null>(null);
  const [segments, setSegments] = useState<HotspotSegment[]>(() => sortByOrdinal(hotspot?.segments ?? []));
  const [matchedOrdinals] = useState<Set<number>>(() => new Set((hotspot?.segments ?? []).map((s) => s.ordinal)));
  const [leadingBounded, setLeadingBounded] = useState(false);
  const [trailingBounded, setTrailingBounded] = useState(false);
  const [isAddingContext, setIsAddingContext] = useState(false);
  const [contextError, setContextError] = useState<string | null>(null);

  if (!hotspot) {
    return (
      <aside className={open ? 'reader open' : 'reader'}>
        <div className="reader-empty">
          <h2>Nothing selected yet</h2>
          <p>Select a hotspot to see its full text and citation here.</p>
        </div>
      </aside>
    );
  }

  const attribution = hotspot.source.citation_label || `${hotspot.source.title}, ${hotspot.source.author}`;
  const hasDimmedMatch =
    activeInterpretant !== null && hotspot.matches.some((match) => match.interpretant !== activeInterpretant);
  const hasGap = segments.some((segment, i) => i > 0 && segment.ordinal - segments[i - 1].ordinal > 1);
  const fullyLoaded = !hasGap && leadingBounded && trailingBounded;

  function goToSegment(ordinal: number) {
    setActiveSegmentOrdinal(ordinal);
    document.getElementById(segmentElementId(hotspot!.regionId, ordinal))?.scrollIntoView({ block: 'nearest' });
  }

  function mergeSegments(newOnes: HotspotSegment[]) {
    if (newOnes.length === 0) return;
    setSegments((prev) => {
      const byOrdinal = new Map(prev.map((segment) => [segment.ordinal, segment]));
      for (const segment of newOnes) byOrdinal.set(segment.ordinal, segment);
      return sortByOrdinal(Array.from(byOrdinal.values()));
    });
  }

  async function handleAddContext() {
    const sourceId = hotspot!.source.id;
    const current = segments;
    const minOrdinal = current[0].ordinal;
    const maxOrdinal = current[current.length - 1].ordinal;

    setIsAddingContext(true);
    setContextError(null);
    try {
      if (hasGap) {
        mergeSegments(await fetchSegments(sourceId, minOrdinal, maxOrdinal));
        return;
      }

      const tasks: Promise<void>[] = [];
      if (!leadingBounded) {
        tasks.push(
          (async () => {
            if (minOrdinal <= 0) {
              setLeadingBounded(true);
              return;
            }
            const probe = await fetchSegments(sourceId, minOrdinal - 1, minOrdinal - 1);
            if (probe.length === 0) {
              setLeadingBounded(true);
              return;
            }
            const edgeSection = current[0].section;
            if (edgeSection !== '' && probe[0].section !== edgeSection) {
              setLeadingBounded(true);
              return;
            }
            mergeSegments(probe);
          })(),
        );
      }
      if (!trailingBounded) {
        tasks.push(
          (async () => {
            const probe = await fetchSegments(sourceId, maxOrdinal + 1, maxOrdinal + 1);
            if (probe.length === 0) {
              setTrailingBounded(true);
              return;
            }
            const edgeSection = current[current.length - 1].section;
            if (edgeSection !== '' && probe[0].section !== edgeSection) {
              setTrailingBounded(true);
              return;
            }
            mergeSegments(probe);
          })(),
        );
      }
      await Promise.all(tasks);
    } catch (error) {
      setContextError(error instanceof Error ? error.message : 'Failed to load context.');
    } finally {
      setIsAddingContext(false);
    }
  }

  function handleCopyRef() {
    void navigator.clipboard.writeText(citationRef(hotspot!));
  }

  return (
    <aside className={open ? 'reader open' : 'reader'}>
      <div className="reader-inner">
        <div className="reader-toolbar">
          {onBack && (
            <button type="button" className="icon-btn reader-back" onClick={onBack} aria-label="Back to list">
              <svg viewBox="0 0 24 24" fill="none">
                <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          )}
          <span className="breadcrumb">
            {attribution} › {hotspotTitle(hotspot)}
          </span>
          <div className="nav-btns">
            <button type="button" onClick={onPrev} disabled={!canGoPrev} aria-label="Previous hotspot">
              <svg viewBox="0 0 24 24" fill="none">
                <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <button type="button" onClick={onNext} disabled={!canGoNext} aria-label="Next hotspot">
              <svg viewBox="0 0 24 24" fill="none">
                <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>

        <div className="reader-title-row">
          <h2>{hotspotTitle(hotspot)}</h2>
          <span className="hc-badge">{convergenceLabel(hotspot.convergenceCount)}</span>
        </div>

        <div className="chip-row">
          {hotspot.matches.map((match) => (
            <button
              type="button"
              key={`${match.interpretant}-${match.segmentOrdinal}`}
              className={
                (activeInterpretant === null || match.interpretant === activeInterpretant
                  ? 'interpretant-chip active'
                  : 'interpretant-chip dimmed') +
                (match.segmentOrdinal === activeSegmentOrdinal ? ' anchored' : '')
              }
              onClick={() => goToSegment(match.segmentOrdinal)}
            >
              {match.interpretant} · {match.kind === 'exact' ? 'exact' : match.score.toFixed(2)}
            </button>
          ))}
        </div>
        {activeInterpretant !== null && hasDimmedMatch && (
          <p className="dimmed-note">(dimmed = matched but outside current filter)</p>
        )}

        <button type="button" className="add-context-button" onClick={handleAddContext} disabled={isAddingContext || fullyLoaded}>
          {isAddingContext ? 'Loading…' : fullyLoaded ? 'Full context loaded' : '+ Add Context'}
        </button>
        {contextError && <p className="error">{contextError}</p>}

        <div className="segment-list">
          {segments.map((segment) => {
            const classes = ['segment'];
            if (!matchedOrdinals.has(segment.ordinal)) classes.push('context');
            if (segment.ordinal === activeSegmentOrdinal) classes.push('active');
            return (
              <div key={segment.ordinal} id={segmentElementId(hotspot.regionId, segment.ordinal)} className={classes.join(' ')}>
                {segment.locator && <p className="segment-locator">{segment.locator}</p>}
                <p className="text">{segment.text}</p>
              </div>
            );
          })}
        </div>

        <div className="reader-footer">
          <button type="button" onClick={onPrev} disabled={!canGoPrev}>
            ← prev hotspot
          </button>
          <button type="button" onClick={handleCopyRef}>
            copy ref
          </button>
          <button type="button" onClick={onNext} disabled={!canGoNext}>
            next hotspot →
          </button>
        </div>
      </div>
    </aside>
  );
}
