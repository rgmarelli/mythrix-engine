import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { AgentCapabilities, AgentCard, AgentInstruction, CommandSpec, Hotspot } from '../api/types';
import type { ThreadItem } from '../state/useTabs';
import { argHintFor, completionOf, matchCommands } from '../utils/commands';
import { hotspotTitle } from '../utils/hotspot';

interface Props {
  items: ThreadItem[];
  isSending: boolean;
  onSend: (message: string) => void;
  onClear: () => void;
  selectedHotspot: Hotspot | null;
  capabilities: AgentCapabilities | null;
}

// `/clear` is implemented here and nowhere else (agent.md FR-AG-22), so it
// keeps working when the capabilities document is unavailable (FR-CAP-15).
// The document governs whether a command is listed and whether it is routed to
// the agent — not whether this viewer can clear a thread.
const CLEAR_COMMAND = '/clear';

function commandOf(message: string): string {
  return message.trim().split(' ')[0].toLowerCase();
}

function isClientHandled(message: string, capabilities: AgentCapabilities | null): boolean {
  const head = commandOf(message);
  if (head === CLEAR_COMMAND) return true;
  return capabilities?.commands.some((command) => command.name === head && command.handledBy === 'client') ?? false;
}

function CommandLabel({ command }: { command: CommandSpec }) {
  return (
    <>
      <code>
        {command.name}
        {command.args ? ` ${command.args}` : ''}
      </code>
      <span>{command.summary}</span>
    </>
  );
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
                {chip.interpretant} · {chip.kind === 'concept' ? chip.score.toFixed(2) : chip.kind}
              </span>
            ))}
          </div>
        ),
      )}
    </>
  );
}

// A `confirm_query` instruction carries the exact command a human would type
// (agnostic-query.md FR-AQ-07); this button sends that same string, so the
// affordance and the typed command are one path, not two (FR-WEB-21).
function ConfirmActions({ instructions, onSend }: { instructions: AgentInstruction[]; onSend: (m: string) => void }) {
  const confirmations = instructions.filter((instruction) => instruction.type === 'confirm_query');
  if (confirmations.length === 0) return null;

  return (
    <div className="chips">
      {confirmations.map((instruction, index) => {
        const command = String(instruction.payload.confirm_command ?? '');
        if (!command) return null;
        return (
          <button type="button" className="confirm-query" key={index} onClick={() => onSend(command)}>
            Run this query
          </button>
        );
      })}
    </div>
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
export function AgentChatPanel({ items, isSending, onSend, onClear, selectedHotspot, capabilities }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [dismissed, setDismissed] = useState(false);

  // Derived, never stored: the list cannot drift from the text it describes.
  const commands = capabilities?.commands ?? [];
  const matches = dismissed ? [] : matchCommands(inputValue, commands);
  const active = matches[activeIndex];
  const completion = completionOf(inputValue, active);
  // Once the name is complete the list stops offering completions and becomes a
  // syntax reminder for the arguments being typed (FR-WEB-24) — nothing to
  // choose, so no entry is active and the key handler stays inert.
  const argHint = dismissed || matches.length > 0 ? null : argHintFor(inputValue, commands);

  function editInput(value: string) {
    setInputValue(value);
    setActiveIndex(0);
    setDismissed(false);
  }

  function accept(name: string) {
    editInput(`${name} `);
  }

  function send(message: string) {
    const trimmed = message.trim();
    if (!trimmed || isSending) return;
    editInput('');
    // A client-handled command never reaches the agent and never appears as a
    // user bubble (FR-CAP-05); everything else is an ordinary turn.
    if (isClientHandled(trimmed, capabilities)) {
      if (commandOf(trimmed) === CLEAR_COMMAND) onClear();
      return;
    }
    onSend(trimmed);
  }

  // Inert unless the completion affordance is showing, so ordinary typing —
  // and Tab's ordinary focus move — behave exactly as before (FR-WEB-22).
  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!active) return;
    if (event.key === 'Tab') {
      event.preventDefault();
      accept(active.name);
    } else if (event.key === 'Enter') {
      // Only a strict prefix completes; a fully typed command falls through to
      // the form's submit, so there is still one send path.
      if (completion) {
        event.preventDefault();
        accept(active.name);
      }
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % matches.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((index) => (index - 1 + matches.length) % matches.length);
    } else if (event.key === 'Escape') {
      setDismissed(true);
    }
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
              <div className="bubble">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.text}</ReactMarkdown>
              </div>
              <AgentCards cards={item.cards} />
              <ConfirmActions instructions={item.instructions} onSend={send} />
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
        {matches.length > 0 && (
          <ul className="command-list">
            {matches.map((command, index) => (
              <li key={command.name}>
                <button
                  type="button"
                  className={index === activeIndex ? 'is-active' : undefined}
                  onClick={() => accept(command.name)}
                >
                  <CommandLabel command={command} />
                </button>
              </li>
            ))}
          </ul>
        )}
        {argHint && (
          <ul className="command-list">
            <li>
              <div className="hint">
                <CommandLabel command={argHint} />
              </div>
            </li>
          </ul>
        )}
        <form
          className="input-row"
          onSubmit={(event) => {
            event.preventDefault();
            send(inputValue);
          }}
        >
          {/* The ghost sits under the input and reproduces the typed text
              transparently, so the remainder lands exactly where the caret is;
              both layers must keep inheriting the same font and padding. */}
          <div className="input-shell">
            {completion && (
              <span className="ghost" aria-hidden="true">
                <span>{inputValue}</span>
                {completion}
              </span>
            )}
            <input
              type="text"
              placeholder="Ask about this hotspot…"
              value={inputValue}
              disabled={isSending}
              onChange={(event) => editInput(event.target.value)}
              onKeyDown={handleKeyDown}
            />
          </div>
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
