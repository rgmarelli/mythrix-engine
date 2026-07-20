import { useState } from 'react';
import { summarizePassage } from '../api/client';
import type { Fragment } from '../api/types';
import { convergenceLabel, fragmentTitle } from '../utils/fragment';

interface Props {
  fragment: Fragment | null;
  activeInterpretant: string | null;
  onPrev: () => void;
  onNext: () => void;
  canGoPrev: boolean;
  canGoNext: boolean;
}

function citationRef(fragment: Fragment): string {
  const attribution = fragment.source.citation_label || `${fragment.source.title}, ${fragment.source.author}`;
  return fragment.locator ? `${attribution} — ${fragment.locator}` : attribution;
}

/** The fragment-centric replacement for `PassageDetailPanel`: full text, full
 * citation, and an on-demand AI summary — plus, new to this redesign, the
 * fragment's complete convergence picture (every matched interpretant, not
 * only the one currently filtered on) and hotspot navigation. Mounted by
 * `App.tsx` with `key={fragment.chunk_id}` so summary/loading/error state
 * never leaks from one fragment to the next. */
export function FragmentDetailPanel({ fragment, activeInterpretant, onPrev, onNext, canGoPrev, canGoNext }: Props) {
  const [summary, setSummary] = useState<string | null>(null);
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  if (!fragment) {
    return (
      <aside className="fragment-detail empty">
        <p>Select a fragment to see its full text and citation here.</p>
      </aside>
    );
  }

  const attribution = fragment.source.citation_label || `${fragment.source.title}, ${fragment.source.author}`;
  const hasDimmedMatch =
    activeInterpretant !== null && fragment.matches.some((match) => match.interpretant !== activeInterpretant);

  async function handleSummarize() {
    setIsSummarizing(true);
    setSummaryError(null);
    try {
      setSummary(await summarizePassage(fragment!.text, fragment!.matches.map((match) => match.interpretant)));
    } catch (error) {
      setSummaryError(error instanceof Error ? error.message : 'Failed to generate a summary.');
    } finally {
      setIsSummarizing(false);
    }
  }

  function handleCopyRef() {
    void navigator.clipboard.writeText(citationRef(fragment!));
  }

  return (
    <aside className="fragment-detail">
      <p className="breadcrumb">
        {attribution} › {fragmentTitle(fragment)}
      </p>
      <div className="title-row">
        <h2>{fragmentTitle(fragment)}</h2>
        <span className="badge">{convergenceLabel(fragment.convergence_count)}</span>
      </div>

      <div className="chip-row">
        {fragment.matches.map((match) => (
          <span
            key={match.interpretant}
            className={
              activeInterpretant === null || match.interpretant === activeInterpretant
                ? 'interpretant-chip active'
                : 'interpretant-chip dimmed'
            }
          >
            {match.interpretant} · {match.score.toFixed(2)}
          </span>
        ))}
      </div>
      {activeInterpretant !== null && hasDimmedMatch && (
        <p className="dimmed-note">(dimmed = matched but outside current filter)</p>
      )}

      <button type="button" className="ai-summary-button" onClick={handleSummarize} disabled={isSummarizing}>
        {isSummarizing ? 'Summarizing…' : 'Generate AI summary'}
      </button>

      <p className="text">{fragment.text}</p>

      {summaryError && <p className="error">{summaryError}</p>}
      {summary && (
        <div className="ai-summary-box">
          <p className="label">AI SUMMARY</p>
          <p>{summary}</p>
        </div>
      )}

      <div className="fragment-footer">
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
