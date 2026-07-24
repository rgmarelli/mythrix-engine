import type { FormEvent } from 'react';
import type { SignSummary, Tradition } from '../api/types';

interface Props {
  signs: SignSummary[];
  traditions: Tradition[];
  selectedSystem: string;
  selectedSymbol: string;
  selectedTradition: string;
  minScore: number | null;
  minScoreDefault: number;
  isStreaming: boolean;
  onSystemChange: (semioticSystem: string) => void;
  onSymbolChange: (slug: string) => void;
  onTraditionChange: (slug: string) => void;
  onMinScoreChange: (value: number | null) => void;
  onSubmit: () => void;
}

/** Restricted to symbol/tradition combinations that have a manifestation
 * (FR-WEB-01): the tradition dropdown only ever lists the selected sign's own
 * `tradition_slugs`, from `/api/symbols` — a `/api/query` error for an
 * unknown sign/tradition/manifestation-less pair is
 * unreachable through normal use of this form. The semiotic-system
 * dropdown (FR-WEB-01) scopes which signs the symbol dropdown offers — its
 * options are the distinct `semiotic_system` values already present in
 * `signs`, no separate endpoint needed. */
export function SignTraditionPicker({
  signs,
  traditions,
  selectedSystem,
  selectedSymbol,
  selectedTradition,
  minScore,
  minScoreDefault,
  isStreaming,
  onSystemChange,
  onSymbolChange,
  onTraditionChange,
  onMinScoreChange,
  onSubmit,
}: Props) {
  const systems = [...new Set(signs.map((s) => s.semiotic_system))].sort();
  const availableSigns = selectedSystem ? signs.filter((s) => s.semiotic_system === selectedSystem) : [];
  const currentSummary = signs.find((s) => s.slug === selectedSymbol);
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
        Semiotic system
        <select
          value={selectedSystem}
          onChange={(event) => {
            onSystemChange(event.target.value);
            onSymbolChange('');
            onTraditionChange('');
          }}
        >
          <option value="" disabled>
            Select a semiotic system…
          </option>
          {systems.map((system) => (
            <option key={system} value={system}>
              {system}
            </option>
          ))}
        </select>
      </label>

      <label>
        Symbol
        <select
          value={selectedSymbol}
          onChange={(event) => {
            onSymbolChange(event.target.value);
            onTraditionChange('');
          }}
          disabled={!selectedSystem}
        >
          <option value="" disabled>
            Select a symbol…
          </option>
          {availableSigns.map((sign) => (
            <option key={sign.slug} value={sign.slug}>
              {sign.canonical_name}
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

      <label>
        Min score
        <input
          type="number"
          min={0}
          max={1}
          step={0.01}
          placeholder={minScoreDefault.toFixed(2)}
          value={minScore ?? ''}
          onChange={(event) => {
            const raw = event.target.value;
            onMinScoreChange(raw === '' ? null : Number(raw));
          }}
          title="Minimum similarity score an interpretant match must clear to appear in results. Leave blank for the server default."
        />
      </label>

      <button type="submit" disabled={!selectedSymbol || !selectedTradition || isStreaming}>
        {isStreaming ? 'Querying…' : 'Explore'}
      </button>
    </form>
  );
}
