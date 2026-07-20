import { useState } from 'react';
import { summarizePassage } from '../api/client';
import type { RetrievedPassage } from '../api/types';

interface Props {
  passage: RetrievedPassage | null;
  concepts: string[];
}

/** The only place a passage's `text` ever renders (FR4, FR5) — full
 * verbatim text, no client-side truncation, plus the complete citation.
 * Metadata (source/locator/tradition/score) is shown first, so it's visible
 * without scrolling past the passage text. Remounted by `App.tsx` on every
 * new passage selection (`key={passage.chunk_id}`) so AI Summary state
 * never leaks from one passage to the next. */
export function PassageDetailPanel({ passage, concepts }: Props) {
  const [summary, setSummary] = useState<string | null>(null);
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  if (!passage) {
    return (
      <aside className="passage-detail empty">
        <p>Select a passage to see its full text and citation here.</p>
      </aside>
    );
  }

  const attribution = [passage.source.title, passage.source.author].filter(Boolean).join(', ');

  async function handleSummarize() {
    setIsSummarizing(true);
    setSummaryError(null);
    try {
      setSummary(await summarizePassage(passage!.text, concepts));
    } catch (error) {
      setSummaryError(error instanceof Error ? error.message : 'Failed to generate a summary.');
    } finally {
      setIsSummarizing(false);
    }
  }

  return (
    <aside className="passage-detail">
      <dl>
        <dt>Source</dt>
        <dd>{attribution}</dd>
        {passage.locator && (
          <>
            <dt>Locator</dt>
            <dd>{passage.locator}</dd>
          </>
        )}
        <dt>Tradition</dt>
        <dd>{passage.tradition.name}</dd>
        <dt>Score</dt>
        <dd>{passage.score.toFixed(2)}</dd>
      </dl>
      <p className="text">{passage.text}</p>
      <div className="ai-summary">
        <button type="button" onClick={handleSummarize} disabled={isSummarizing}>
          {isSummarizing ? 'Summarizing…' : `AI Summary — ${concepts.join(', ')}`}
        </button>
        {summaryError && <p className="error">{summaryError}</p>}
        {summary && <p className="summary-text">{summary}</p>}
      </div>
    </aside>
  );
}
