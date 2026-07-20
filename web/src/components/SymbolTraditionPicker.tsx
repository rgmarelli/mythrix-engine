import type { FormEvent } from 'react';
import type { SymbolSummary, Tradition } from '../api/types';

interface Props {
  symbols: SymbolSummary[];
  traditions: Tradition[];
  selectedSymbol: string;
  selectedTradition: string;
  isStreaming: boolean;
  onSymbolChange: (slug: string) => void;
  onTraditionChange: (slug: string) => void;
  onSubmit: () => void;
}

/** Restricted to symbol/tradition combinations that have an interpretation
 * (FR2): the tradition dropdown only ever lists the selected symbol's own
 * `tradition_slugs`, from `/api/symbols` — a `/api/query` FR9 error is
 * unreachable through normal use of this form. */
export function SymbolTraditionPicker({
  symbols,
  traditions,
  selectedSymbol,
  selectedTradition,
  isStreaming,
  onSymbolChange,
  onTraditionChange,
  onSubmit,
}: Props) {
  const currentSummary = symbols.find((s) => s.slug === selectedSymbol);
  const availableTraditions = currentSummary
    ? traditions.filter((t) => currentSummary.tradition_slugs.includes(t.slug))
    : [];

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onSubmit();
  }

  return (
    <form className="picker" onSubmit={handleSubmit}>
      <label>
        Symbol
        <select
          value={selectedSymbol}
          onChange={(event) => {
            onSymbolChange(event.target.value);
            onTraditionChange('');
          }}
        >
          <option value="" disabled>
            Select a symbol…
          </option>
          {symbols.map((symbol) => (
            <option key={symbol.slug} value={symbol.slug}>
              {symbol.canonical_name}
            </option>
          ))}
        </select>
      </label>

      <label>
        Tradition
        <select
          value={selectedTradition}
          onChange={(event) => onTraditionChange(event.target.value)}
          disabled={!selectedSymbol}
        >
          <option value="" disabled>
            Select a tradition…
          </option>
          {availableTraditions.map((tradition) => (
            <option key={tradition.slug} value={tradition.slug}>
              {tradition.name}
            </option>
          ))}
        </select>
      </label>

      <button type="submit" disabled={!selectedSymbol || !selectedTradition || isStreaming}>
        {isStreaming ? 'Querying…' : 'Query'}
      </button>
    </form>
  );
}
