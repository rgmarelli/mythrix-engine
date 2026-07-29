// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

interface Option {
  id: string;
  label: string;
  count: number;
}

interface Props {
  title: string;
  allLabel: string;
  allCount: number;
  options: Option[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  search?: string;
  onSearchChange?: (value: string) => void;
  searchPlaceholder?: string;
}

/** One facet row (Sources or Interpretants) in the control panel sidebar —
 * an "All" row plus one row per option, single-select. Both rows are
 * structurally identical, so this one component renders either. When
 * `search`/`onSearchChange` are both supplied (Interpretants only, master
 * specs/interfaces/web-viewer.md FR-WEB-13), a text filter narrows which options are listed without
 * touching counts or selection. */
export function FacetRow({
  title,
  allLabel,
  allCount,
  options,
  selected,
  onSelect,
  search,
  onSearchChange,
  searchPlaceholder,
}: Props) {
  const searchable = search !== undefined && onSearchChange !== undefined;
  return (
    <section className="panel-section facet-row">
      <h2>{title}</h2>
      {searchable && (
        <div className="facet-search">
          <svg viewBox="0 0 24 24" fill="none">
            <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.8" />
            <path d="M21 21l-4.3-4.3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          <input
            type="text"
            value={search}
            placeholder={searchPlaceholder ?? 'Filter…'}
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </div>
      )}
      <div className="facet-list">
        <button type="button" className={selected === null ? 'facet-item active' : 'facet-item'} onClick={() => onSelect(null)}>
          <span className="name">
            <span className="label-text">{allLabel}</span>
          </span>
          <span className="count">{allCount}</span>
        </button>
        {options.map((option) => (
          <button
            type="button"
            key={option.id}
            className={selected === option.id ? 'facet-item active' : 'facet-item'}
            onClick={() => onSelect(option.id)}
          >
            <span className="name">
              <span className="label-text" title={option.label}>
                {option.label}
              </span>
            </span>
            <span className="count">{option.count}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
