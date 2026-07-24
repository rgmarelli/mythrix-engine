import type { SignSummary } from '../api/types';
import type { Tab } from '../state/useTabs';
import { TabStrip } from './TabStrip';

interface Props {
  tabs: Tab[];
  activeTabId: string;
  signs: SignSummary[];
  onSelectTab: (id: string) => void;
  onCloseTab: (id: string) => void;
  onAddTab: () => void;
  onToggleFilters: () => void;
}

/** The app's top bar (specs/tabbed-workspace-redesign FR92) — brand mark plus
 * the tab strip. Replaces the plain `<header>` the single-query viewer used
 * before tabs existed. */
export function TopBar({ tabs, activeTabId, signs, onSelectTab, onCloseTab, onAddTab, onToggleFilters }: Props) {
  return (
    <header className="topbar">
      <button type="button" className="icon-btn filters-toggle" aria-label="Open filters" onClick={onToggleFilters}>
        <svg viewBox="0 0 24 24" fill="none">
          <path d="M4 6h16M7 12h10M10 18h4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      </button>
      <div className="brand">
        <div className="mark">
          <svg viewBox="0 0 64 64">
            <line x1="32" y1="10" x2="32" y2="24" stroke="#33518F" strokeWidth="2" strokeLinecap="round" />
            <line x1="32" y1="40" x2="32" y2="54" stroke="#33518F" strokeWidth="2" strokeLinecap="round" />
            <line x1="10" y1="32" x2="24" y2="32" stroke="#33518F" strokeWidth="2" strokeLinecap="round" />
            <line x1="40" y1="32" x2="54" y2="32" stroke="#33518F" strokeWidth="2" strokeLinecap="round" />
            <circle cx="32" cy="32" r="4" fill="#A5761F" />
          </svg>
        </div>
        <div className="brand-text">
          <span className="name">Mythrix</span>
          <span className="tagline">Semiotic concordance</span>
        </div>
      </div>
      <TabStrip tabs={tabs} activeTabId={activeTabId} signs={signs} onSelect={onSelectTab} onClose={onCloseTab} onAdd={onAddTab} />
    </header>
  );
}
