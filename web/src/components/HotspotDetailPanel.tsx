// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { extendContext } from '../api/client';
import type { Augmentation, ExtendedRegionRef, Hotspot, HotspotSegment } from '../api/types';
import { convergenceLabel, hotspotTitle } from '../utils/hotspot';
import { ConvergenceIcon } from './ConvergenceIcon';
import { SparkleIcon } from './SparkleIcon';

export type { ExtendedRegionRef } from '../api/types';

interface Props {
  hotspot: Hotspot | null;
  hasResult: boolean;
  augmentation: Augmentation | null;
  onPrev: () => void;
  onNext: () => void;
  canGoPrev: boolean;
  canGoNext: boolean;
  onBack?: () => void;
  open?: boolean;
  // The persisted extension for *this* hotspot, if any — the caller looks
  // this up by the hotspot's own regionId (`useTabs.ts`'s
  // `activeExtendedRegion`), so this component itself needs no hotspot
  // identity bookkeeping of its own.
  initialExtendedRegion?: ExtendedRegionRef;
  onContextExtended?: (region: ExtendedRegionRef) => void;
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
 * interpretant chip linking to the specific segment it anchors to (FR-RK-09) —
 * clicking a chip scrolls to and highlights that segment — plus hotspot
 * navigation. Mounted by `App.tsx` with `key={hotspot.regionId}` so all of
 * this state never leaks from one hotspot to the next. */
export function HotspotDetailPanel({
  hotspot,
  hasResult,
  augmentation,
  onPrev,
  onNext,
  canGoPrev,
  canGoNext,
  onBack,
  open,
  initialExtendedRegion,
  onContextExtended,
}: Props) {
  const [activeSegmentOrdinal, setActiveSegmentOrdinal] = useState<number | null>(null);
  const [segments, setSegments] = useState<HotspotSegment[]>(() =>
    sortByOrdinal(initialExtendedRegion?.segments ?? hotspot?.segments ?? []),
  );
  const [matchedOrdinals] = useState<Set<number>>(() => new Set((hotspot?.segments ?? []).map((s) => s.ordinal)));
  const [leadingBounded, setLeadingBounded] = useState(() => initialExtendedRegion?.leadingBounded ?? false);
  const [trailingBounded, setTrailingBounded] = useState(() => initialExtendedRegion?.trailingBounded ?? false);
  // Mirrors exactly what's been reported to `onContextExtended` — drives
  // whether "Clear Context" is shown, and is what gets restored if the user
  // navigates away and back to this hotspot.
  const [extension, setExtension] = useState<ExtendedRegionRef>(() => initialExtendedRegion ?? null);
  const [isAddingContext, setIsAddingContext] = useState(false);
  const [contextError, setContextError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  if (!hotspot) {
    return (
      <aside className={open ? 'reader open' : 'reader'}>
        {hasResult && (
          <div className="reader-empty">
            <ConvergenceIcon />
            <h2>Nothing selected yet</h2>
            <p>Choose a hotspot on the left to read its source text, see which interpretants converge there, and ground the agent in that passage.</p>
          </div>
        )}
      </aside>
    );
  }

  const attribution = hotspot.source.citation_label || `${hotspot.source.title}, ${hotspot.source.author}`;
  const fullyLoaded = leadingBounded && trailingBounded;

  function goToSegment(ordinal: number) {
    setActiveSegmentOrdinal(ordinal);
    document.getElementById(segmentElementId(hotspot!.regionId, ordinal))?.scrollIntoView({ block: 'nearest' });
  }

  async function handleAddContext() {
    const sourceId = hotspot!.source.id;
    const current = segments;
    const minOrdinal = current[0].ordinal;
    const maxOrdinal = current[current.length - 1].ordinal;

    setIsAddingContext(true);
    setContextError(null);
    try {
      // The backend fills any internal gap first and only that; edge growth
      // happens once no gap remains (FR-CE-02/03,
      // specs/tmp/hotspot-context-expansion-agent) — `current.length` tells
      // it whether the caller's current range is already gap-free.
      const extended = await extendContext(sourceId, minOrdinal, maxOrdinal, current.length);
      setSegments(sortByOrdinal(extended.segments));
      setLeadingBounded(extended.leadingBounded);
      setTrailingBounded(extended.trailingBounded);
      // `region_id` alone can't tell us whether anything actually grew: it
      // encodes only the window's min/max ordinals, and a gap-fill adds
      // segments *inside* that range without moving either end, so it never
      // changes `region_id` — comparing against `hotspot.regionId` would
      // wrongly treat a gap-fill as a no-op. Segment *count* against the
      // hotspot's own original segments is the correct test: a gap-fill,
      // like an edge grow, can only ever add segments, never remove any.
      const next: ExtendedRegionRef = extended.segments.length > hotspot!.segments.length ? extended : null;
      setExtension(next);
      onContextExtended?.(next);
    } catch (error) {
      setContextError(error instanceof Error ? error.message : 'Failed to load context.');
    } finally {
      setIsAddingContext(false);
    }
  }

  function handleClearContext() {
    setSegments(sortByOrdinal(hotspot!.segments));
    setLeadingBounded(false);
    setTrailingBounded(false);
    setExtension(null);
    setContextError(null);
    onContextExtended?.(null);
  }

  function handleCopyRef() {
    void navigator.clipboard.writeText(citationRef(hotspot!));
    setCopied(true);
    setTimeout(() => setCopied(false), 1300);
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
          <div className="breadcrumb-group">
            <span className="breadcrumb">
              {attribution} › {hotspotTitle(hotspot)}
            </span>
          </div>
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
              className={'interpretant-chip' + (match.segmentOrdinal === activeSegmentOrdinal ? ' anchored' : '')}
              onClick={() => goToSegment(match.segmentOrdinal)}
            >
              {match.interpretant} · {match.kind === 'concept' ? match.score.toFixed(2) : match.kind}
            </button>
          ))}
        </div>

        {/* Generated, and marked as such — placed above the actions so it
            precedes the verbatim segment list and cannot read as part of the
            source text (specs/interfaces/augmentation.md FR-AU-28). */}
        {augmentation && (
          <div className="augmented-section">
            <div className="augmented-head">
              <SparkleIcon />
              <span>AI analysis</span>
            </div>
            <div className="augmented-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{augmentation.text}</ReactMarkdown>
            </div>
          </div>
        )}

        <div className="reader-actions">
          <div className="context-actions">
            <button type="button" className="add-context-button" onClick={handleAddContext} disabled={isAddingContext || fullyLoaded}>
              {isAddingContext ? 'Loading…' : fullyLoaded ? 'Full context loaded' : '+ Add Context'}
            </button>
            {extension && (
              <button
                type="button"
                className="clear-context-button"
                onClick={handleClearContext}
                disabled={isAddingContext}
              >
                - Clear Context
              </button>
            )}
          </div>
          <button type="button" className={copied ? 'copy-ref-btn copied' : 'copy-ref-btn'} onClick={handleCopyRef}>
            {copied ? (
              <svg viewBox="0 0 24 24" fill="none">
                <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none">
                <rect x="9" y="9" width="11" height="11" rx="2" stroke="currentColor" strokeWidth="1.6" />
                <path d="M5 15V5a2 2 0 0 1 2-2h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            )}
            {copied ? 'Copied' : 'Copy reference'}
          </button>
        </div>
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
      </div>
    </aside>
  );
}
