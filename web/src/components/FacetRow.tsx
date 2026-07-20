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
}

/** One facet row (Sources or Interpretants) — an "All" chip plus one chip per
 * option, single-select. Both rows are structurally identical, so this one
 * component renders either. */
export function FacetRow({ title, allLabel, allCount, options, selected, onSelect }: Props) {
  return (
    <section className="facet-row">
      <h2>{title}</h2>
      <div className="chip-row">
        <button type="button" className={selected === null ? 'chip active' : 'chip'} onClick={() => onSelect(null)}>
          {allLabel} ({allCount})
        </button>
        {options.map((option) => (
          <button
            type="button"
            key={option.id}
            className={selected === option.id ? 'chip active' : 'chip'}
            onClick={() => onSelect(option.id)}
          >
            {option.label} ({option.count})
          </button>
        ))}
      </div>
    </section>
  );
}
