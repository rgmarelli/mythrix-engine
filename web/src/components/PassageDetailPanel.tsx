import type { RetrievedPassage } from '../api/types';

interface Props {
  passage: RetrievedPassage | null;
}

/** The only place a passage's `text` ever renders (FR4, FR5) — full
 * verbatim text, no client-side truncation, plus the complete citation. */
export function PassageDetailPanel({ passage }: Props) {
  if (!passage) {
    return (
      <aside className="passage-detail empty">
        <p>Select a passage to see its full text and citation here.</p>
      </aside>
    );
  }

  const attribution = [passage.source.title, passage.source.author].filter(Boolean).join(', ');

  return (
    <aside className="passage-detail">
      <p className="text">{passage.text}</p>
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
    </aside>
  );
}
