import { useState } from 'react';
import type { AgentCard, Hotspot } from '../api/types';
import type { ThreadItem } from '../state/useTabs';
import { hotspotTitle } from '../utils/hotspot';

interface Props {
  items: ThreadItem[];
  isSending: boolean;
  onSend: (message: string) => void;
  onClear: () => void;
  selectedHotspot: Hotspot | null;
}

function AgentMark({ thinking }: { thinking?: boolean }) {
  return (
    <div className={thinking ? 'mark thinking' : 'mark'}>
      <svg viewBox="0 0 64 64">
        <line x1="32" y1="12" x2="32" y2="24" stroke="#6D28D9" strokeWidth="2" strokeLinecap="round" />
        <line x1="32" y1="40" x2="32" y2="52" stroke="#6D28D9" strokeWidth="2" strokeLinecap="round" />
        <line x1="12" y1="32" x2="24" y2="32" stroke="#6D28D9" strokeWidth="2" strokeLinecap="round" />
        <line x1="40" y1="32" x2="52" y2="32" stroke="#6D28D9" strokeWidth="2" strokeLinecap="round" />
        <circle className="core" cx="32" cy="32" r="4" fill="#6D28D9" />
      </svg>
    </div>
  );
}

function AiAvatar() {
  return (
    <div className="ai-mark">
      <svg viewBox="0 0 64 64">
        <line x1="32" y1="12" x2="32" y2="24" stroke="#6D28D9" strokeWidth="2" strokeLinecap="round" />
        <line x1="32" y1="40" x2="32" y2="52" stroke="#6D28D9" strokeWidth="2" strokeLinecap="round" />
        <line x1="12" y1="32" x2="24" y2="32" stroke="#6D28D9" strokeWidth="2" strokeLinecap="round" />
        <line x1="40" y1="32" x2="52" y2="32" stroke="#6D28D9" strokeWidth="2" strokeLinecap="round" />
        <circle cx="32" cy="32" r="4" fill="#6D28D9" />
      </svg>
    </div>
  );
}

function contextStripText(hotspot: Hotspot | null): string {
  if (!hotspot) return 'no hotspot selected yet';
  const interpretants = hotspot.matches.map((match) => match.interpretant).join(', ');
  return interpretants ? `reading ${hotspotTitle(hotspot)} · interpretants: ${interpretants}` : `reading ${hotspotTitle(hotspot)}`;
}

function AgentCards({ cards }: { cards: AgentCard[] }) {
  return (
    <>
      {cards.map((card, index) =>
        card.type === 'citation' ? (
          <div className="verse" key={index}>
            {(card.sourceLabel || card.locator) && (
              <span className="cite">{[card.sourceLabel, card.locator].filter(Boolean).join(' · ').toUpperCase()}</span>
            )}
            {card.text && `"${card.text}"`}
          </div>
        ) : (
          <div className="chips" key={index}>
            {card.chips.map((chip) => (
              <span className="chip" key={`${chip.interpretant}-${chip.segmentOrdinal}`}>
                {chip.interpretant} · {chip.kind === 'exact' ? 'exact' : chip.score.toFixed(2)}
              </span>
            ))}
          </div>
        ),
      )}
    </>
  );
}

/** Docked, floating chat panel grounded in the active hotspot
 * (specs/interfaces/agent.md FR-AG-14–FR-AG-22), now a controlled view onto whichever tab is
 * active (FR-WEB-10): `items`/`isSending` and the
 * `onSend` network call are owned by `useTabs`, scoped per tab, so switching
 * tabs simply re-renders this same instance against different data. Only the
 * composer's live text and the dock's collapsed/expanded chrome stay local —
 * neither is tab-scoped (FR-WEB-10).
 *
 * Collapse/expand is a single persistent element with a `collapsed` class
 * toggle, not a branch into a different element — that's what lets
 * `.agent-dock`'s `transition: height, width` actually animate; two
 * different DOM trees can't transition into each other. */
export function AgentChatPanel({ items, isSending, onSend, onClear, selectedHotspot }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const [inputValue, setInputValue] = useState('');

  function handleSend() {
    const message = inputValue.trim();
    if (!message || isSending) return;
    setInputValue('');
    // `/clear` is a composer command, not a chat message: it never reaches
    // the agent or appears as a user bubble, it just wipes this tab's thread
    // and starts a fresh session.
    if (message.toLowerCase() === '/clear') {
      onClear();
      return;
    }
    onSend(message);
  }

  return (
    <div className={collapsed ? 'agent-dock collapsed' : 'agent-dock'}>
      <div
        className="dock-head"
        onClick={() => {
          if (collapsed) setCollapsed(false);
        }}
      >
        <AgentMark thinking={isSending} />
        <div className="head-text">
          <div className="head-title">Mythrix Agent</div>
        </div>
        <button
          type="button"
          className="dock-collapse"
          onClick={(event) => {
            event.stopPropagation();
            setCollapsed((prev) => !prev);
          }}
          aria-label={collapsed ? 'Expand agent panel' : 'Collapse agent panel'}
        >
          –
        </button>
      </div>

      <div className="ctx-strip">
        <span className="dot" />
        <span>{contextStripText(selectedHotspot)}</span>
      </div>

      <div className="thread">
        {items.map((item) => {
          if (item.kind === 'user') {
            return (
              <div className="msg user" key={item.id}>
                <div className="bubble">{item.text}</div>
              </div>
            );
          }
          if (item.kind === 'reset') {
            return <div className="reset-divider" key={item.id}>{item.label}</div>;
          }
          if (item.kind === 'error') {
            return (
              <div className="msg ai" key={item.id}>
                <AiAvatar />
                <div className="agent-error">{item.text}</div>
              </div>
            );
          }
          return (
            <div className="msg ai" key={item.id}>
              <AiAvatar />
              <div className="bubble">{item.text}</div>
              <AgentCards cards={item.cards} />
            </div>
          );
        })}
        {isSending && (
          <div className="msg ai">
            <AiAvatar />
            <div className="bubble thinking-bubble" aria-live="polite">
              <span className="thinking-dots">
                <span />
                <span />
                <span />
              </span>
            </div>
          </div>
        )}
      </div>

      <div className="composer">
        <form
          className="input-row"
          onSubmit={(event) => {
            event.preventDefault();
            handleSend();
          }}
        >
          <input
            type="text"
            placeholder="Ask about this hotspot…"
            value={inputValue}
            disabled={isSending}
            onChange={(event) => setInputValue(event.target.value)}
          />
          <button type="submit" className="send" disabled={isSending || !inputValue.trim()}>
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M4 12L20 4L14 20L11 13L4 12Z" fill="white" />
            </svg>
          </button>
        </form>
      </div>
    </div>
  );
}
