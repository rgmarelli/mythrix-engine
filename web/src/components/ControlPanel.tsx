// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import type { SignSummary, Tradition } from '../api/types';
import { FacetRow } from './FacetRow';
import { SignTraditionPicker } from './SignTraditionPicker';

interface FacetOption {
  id: string;
  label: string;
  count: number;
}

interface Props {
  signs: SignSummary[];
  traditions: Tradition[];
  selectedSystem: string;
  selectedSign: string;
  selectedTradition: string;
  minScore: number | null;
  minScoreDefault: number;
  isStreaming: boolean;
  onSystemChange: (semioticSystem: string) => void;
  onSignChange: (slug: string) => void;
  onTraditionChange: (slug: string) => void;
  onMinScoreChange: (value: number | null) => void;
  onSubmit: () => void;
  loadError: string | null;
  queryError: string | null;
  hasResult: boolean;
  sourceOptions: FacetOption[];
  sourceAllCount: number;
  selectedSourceId: string | null;
  onSelectSourceId: (id: string | null) => void;
  interpretantOptions: FacetOption[];
  interpretantAllCount: number;
  selectedInterpretant: string | null;
  onSelectInterpretant: (id: string | null) => void;
  interpretantSearch: string;
  onInterpretantSearchChange: (value: string) => void;
  open: boolean;
}

/** The left sidebar (specs/interfaces/web-viewer.md FR-WEB-14) composing the query
 * form and both facet rows in one column — a pure layout composition, no new
 * logic: `SignTraditionPicker` and `FacetRow` are unchanged/lightly-extended
 * components, just placed together here instead of split across the old
 * header + main. */
export function ControlPanel({
  signs,
  traditions,
  selectedSystem,
  selectedSign,
  selectedTradition,
  minScore,
  minScoreDefault,
  isStreaming,
  onSystemChange,
  onSignChange,
  onTraditionChange,
  onMinScoreChange,
  onSubmit,
  loadError,
  queryError,
  hasResult,
  sourceOptions,
  sourceAllCount,
  selectedSourceId,
  onSelectSourceId,
  interpretantOptions,
  interpretantAllCount,
  selectedInterpretant,
  onSelectInterpretant,
  interpretantSearch,
  onInterpretantSearchChange,
  open,
}: Props) {
  return (
    <aside className={open ? 'control-panel open' : 'control-panel'}>
      <div className="panel-section">
        <h2>Query</h2>
        {loadError && <p className="load-error">{loadError}</p>}
        <SignTraditionPicker
          signs={signs}
          traditions={traditions}
          selectedSystem={selectedSystem}
          selectedSign={selectedSign}
          selectedTradition={selectedTradition}
          minScore={minScore}
          minScoreDefault={minScoreDefault}
          isStreaming={isStreaming}
          onSystemChange={onSystemChange}
          onSignChange={onSignChange}
          onTraditionChange={onTraditionChange}
          onMinScoreChange={onMinScoreChange}
          onSubmit={onSubmit}
        />
        {queryError && <p className="error">{queryError}</p>}
      </div>

      {hasResult && (
        <>
          <FacetRow
            title="Sources"
            allLabel="All sources"
            allCount={sourceAllCount}
            options={sourceOptions}
            selected={selectedSourceId}
            onSelect={onSelectSourceId}
          />
          <FacetRow
            title="Interpretants"
            allLabel="All"
            allCount={interpretantAllCount}
            options={interpretantOptions}
            selected={selectedInterpretant}
            onSelect={onSelectInterpretant}
            search={interpretantSearch}
            onSearchChange={onInterpretantSearchChange}
            searchPlaceholder="Filter interpretants…"
          />
        </>
      )}
    </aside>
  );
}
