import type { SignSummary } from '../api/types';
import type { Tab } from '../state/useTabs';

interface Props {
  tabs: Tab[];
  activeTabId: string;
  signs: SignSummary[];
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
  onAdd: () => void;
}

function tabLabel(tab: Tab, signs: SignSummary[]): string {
  if (!tab.queryResult) return 'New query';
  return signs.find((s) => s.slug === tab.selectedSign)?.canonical_name ?? 'Untitled query';
}

/** The tab strip in the top bar (master spec.md FR-WEB-07/FR-WEB-08) — pure rendering
 * plus the three callbacks; all tab state lives in `useTabs`. */
export function TabStrip({ tabs, activeTabId, signs, onSelect, onClose, onAdd }: Props) {
  return (
    <nav className="tabstrip">
      {tabs.map((tab) => (
        <div
          key={tab.id}
          className={tab.id === activeTabId ? 'tab active' : 'tab'}
          onClick={() => onSelect(tab.id)}
        >
          <span className="tab-label">{tabLabel(tab, signs)}</span>
          <button
            type="button"
            className="tab-close"
            aria-label="Close tab"
            onClick={(event) => {
              event.stopPropagation();
              onClose(tab.id);
            }}
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" className="tab-add" aria-label="New tab" onClick={onAdd}>
        +
      </button>
    </nav>
  );
}
