import { useState } from 'react';
import { postAgentTurn } from '../api/client';
import type { AgentCard, AgentUiSelection, Hotspot } from '../api/types';
import { hotspotTitle } from '../utils/hotspot';

interface Props {
  selectedSystem: string;
  selectedSymbol: string;
  selectedTradition: string;
  minScore: number | null;
  selectedSourceId: string | null;
  selectedInterpretant: string | null;
  selectedRegionId: string | null;
  selectedHotspot: Hotspot | null;
}

type ThreadItem =
  | { kind: 'user'; id: string; text: string }
  | { kind: 'ai'; id: string; text: string; cards: AgentCard[] }
  | { kind: 'reset'; id: string; label: string }
  | { kind: 'error'; id: string; text: string };

let nextItemId = 0;
function itemId(): string {
  nextItemId += 1;
  return `item-${nextItemId}`;
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
 * (specs/in-app-agent-chat) — replaces the removed "Generate AI summary"
 * button with an ordinary chat request ("summarize this"). Owns its own
 * thread/composer state and `sessionId`; the parent only ever hands over the
 * current UI selection, as-is, each turn (FR4) — this component never fires
 * a query or navigates on its own (v0 scope). */
export function AgentChatPanel({
  selectedSystem,
  selectedSymbol,
  selectedTradition,
  minScore,
  selectedSourceId,
  selectedInterpretant,
  selectedRegionId,
  selectedHotspot,
}: Props) {
  const [sessionId] = useState(() => crypto.randomUUID());
  const [collapsed, setCollapsed] = useState(false);
  const [items, setItems] = useState<ThreadItem[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isSending, setIsSending] = useState(false);

  async function handleSend() {
    const message = inputValue.trim();
    if (!message || isSending) return;

    const uiSelection: AgentUiSelection = {
      semioticSystem: selectedSystem || null,
      sign: selectedSymbol || null,
      tradition: selectedTradition || null,
      sourceId: selectedSourceId,
      interpretant: selectedInterpretant,
      minScore,
      regionId: selectedRegionId,
    };

    setInputValue('');
    setIsSending(true);
    const userItem: ThreadItem = { kind: 'user', id: itemId(), text: message };
    setItems((prev) => [...prev, userItem]);

    try {
      const result = await postAgentTurn(sessionId, message, uiSelection);
      const aiItem: ThreadItem = { kind: 'ai', id: itemId(), text: result.replyText, cards: result.cards };
      if (result.threadReset) {
        const label = selectedHotspot ? `now reading ${hotspotTitle(selectedHotspot)}` : 'new thread';
        setItems([{ kind: 'reset', id: itemId(), label }, userItem, aiItem]);
      } else {
        setItems((prev) => [...prev, aiItem]);
      }
    } catch (error) {
      const errorItem: ThreadItem = {
        kind: 'error',
        id: itemId(),
        text: error instanceof Error ? error.message : 'Something went wrong reaching the agent.',
      };
      setItems((prev) => [...prev, errorItem]);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <div className="agent-dock">
      <div className="dock-head">
        <AgentMark thinking={isSending} />
        <div className="head-text">
          <div className="head-title">Mythrix Agent</div>
        </div>
        <button
          type="button"
          className="dock-collapse"
          onClick={() => setCollapsed((prev) => !prev)}
          aria-label={collapsed ? 'Expand agent panel' : 'Collapse agent panel'}
        >
          {collapsed ? '+' : '–'}
        </button>
      </div>

      {!collapsed && (
        <>
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
                void handleSend();
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
        </>
      )}
    </div>
  );
}
