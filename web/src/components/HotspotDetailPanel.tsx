import { useState } from 'react';
import { summarizePassage } from '../api/client';
import type { Hotspot } from '../api/types';
import { convergenceLabel, hotspotTitle } from '../utils/hotspot';

interface Props {
  hotspot: Hotspot | null;
  activeInterpretant: string | null;
  onPrev: () => void;
  onNext: () => void;
  canGoPrev: boolean;
  canGoNext: boolean;
}

function citationRef(hotspot: Hotspot): string {
  const attribution = hotspot.source.citation_label || `${hotspot.source.title}, ${hotspot.source.author}`;
  return hotspot.locator ? `${attribution} — ${hotspot.locator}` : attribution;
}

function segmentElementId(regionId: string, ordinal: number): string {
  return `segment-${regionId}-${ordinal}`;
}

/** A hotspot's constituent segments rendered individually (never one merged blob), each
 * interpretant chip linking to the specific segment it anchors to (FR17) —
 * clicking a chip scrolls to and highlights that segment — plus an on-demand
 * AI summary over every one of the hotspot's segments and hotspot
 * navigation. Mounted by `App.tsx` with `key={hotspot.regionId}` so
 * summary/loading/error state never leaks from one hotspot to the next. */
export function HotspotDetailPanel({ hotspot, activeInterpretant, onPrev, onNext, canGoPrev, canGoNext }: Props) {
  const [summary, setSummary] = useState<string | null>(null);
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [activeSegmentOrdinal, setActiveSegmentOrdinal] = useState<number | null>(null);

  if (!hotspot) {
    return (
      <aside className="hotspot-detail empty">
        <p>Select a hotspot to see its full text and citation here.</p>
      </aside>
    );
  }

  const attribution = hotspot.source.citation_label || `${hotspot.source.title}, ${hotspot.source.author}`;
  const hasDimmedMatch =
    activeInterpretant !== null && hotspot.matches.some((match) => match.interpretant !== activeInterpretant);

  function goToSegment(ordinal: number) {
    setActiveSegmentOrdinal(ordinal);
    document.getElementById(segmentElementId(hotspot!.regionId, ordinal))?.scrollIntoView({ block: 'nearest' });
  }

  async function handleSummarize() {
    setIsSummarizing(true);
    setSummaryError(null);
    try {
      const passageText = hotspot!.segments.map((segment) => segment.text).join('\n\n');
      setSummary(await summarizePassage(passageText, hotspot!.matches.map((match) => match.interpretant)));
    } catch (error) {
      setSummaryError(error instanceof Error ? error.message : 'Failed to generate a summary.');
    } finally {
      setIsSummarizing(false);
    }
  }

  function handleCopyRef() {
    void navigator.clipboard.writeText(citationRef(hotspot!));
  }

  return (
    <aside className="hotspot-detail">
      <p className="breadcrumb">
        {attribution} › {hotspotTitle(hotspot)}
      </p>
      <div className="title-row">
        <h2>{hotspotTitle(hotspot)}</h2>
        <span className="badge">{convergenceLabel(hotspot.convergenceCount)}</span>
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

      <button type="button" className="ai-summary-button" onClick={handleSummarize} disabled={isSummarizing}>
        {isSummarizing ? 'Summarizing…' : 'Generate AI summary'}
      </button>

      <div className="segment-list">
        {hotspot.segments.map((segment) => (
          <div
            key={segment.ordinal}
            id={segmentElementId(hotspot.regionId, segment.ordinal)}
            className={segment.ordinal === activeSegmentOrdinal ? 'segment active' : 'segment'}
          >
            {segment.locator && <p className="segment-locator">{segment.locator}</p>}
            <p className="text">{segment.text}</p>
          </div>
        ))}
      </div>

      {summaryError && <p className="error">{summaryError}</p>}
      {summary && (
        <div className="ai-summary-box">
          <p className="label">AI SUMMARY</p>
          <p>{summary}</p>
        </div>
      )}

      <div className="hotspot-footer">
        <button type="button" onClick={onPrev} disabled={!canGoPrev}>
          ← prev hotspot
        </button>
        <button type="button" onClick={onNext} disabled={!canGoNext}>
          next hotspot →
        </button>
        <button type="button" onClick={handleCopyRef}>
          copy ref
        </button>
      </div>
    </aside>
  );
}
