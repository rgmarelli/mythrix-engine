// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ComponentProps } from 'react';
import { AgentChatPanel } from './AgentChatPanel';
import { makeHotspot } from '../test/fixtures';
import type { ThreadItem } from '../state/useTabs';
import type { AgentCapabilities } from '../api/types';

const CAPABILITIES: AgentCapabilities = {
  commands: [
    { name: '/clear', args: null, summary: 'Clear this thread', handledBy: 'client', listed: true },
    { name: '/summarize', args: null, summary: 'Summarize this region', handledBy: 'server', listed: true },
    { name: '/query', args: 'term[:exact|:filter], …', summary: 'Search on your own terms', handledBy: 'server', listed: true },
    { name: '/query-confirm', args: '<id>', summary: 'Run a parsed ad-hoc query', handledBy: 'server', listed: false },
    {
      name: '/discover',
      args: '"what to look for", term[:exact|:filter], …',
      summary: 'Search, read every result against a question, and consolidate',
      handledBy: 'server',
      listed: true,
    },
    { name: '/augment-confirm', args: '<id>', summary: 'Run a parsed discovery', handledBy: 'server', listed: false },
  ],
  bindings: { confirm_query: null, confirm_augment: null },
};

function renderPanel(overrides: Partial<ComponentProps<typeof AgentChatPanel>> = {}) {
  const props: ComponentProps<typeof AgentChatPanel> = {
    items: [],
    isSending: false,
    onSend: vi.fn(),
    onClear: vi.fn(),
    onNavigateRegion: vi.fn(),
    selectedHotspot: null,
    capabilities: CAPABILITIES,
    ...overrides,
  };
  render(<AgentChatPanel {...props} />);
  return props;
}

it('shows "no hotspot selected yet" in the context strip when nothing is selected', () => {
  renderPanel({ selectedHotspot: null });
  expect(screen.getByText('no hotspot selected yet')).toBeInTheDocument();
});

it('shows the hotspot title and its matched interpretants in the context strip', () => {
  const hotspot = makeHotspot({
    locator: 'Ecclesiasticus 43:1',
    matches: [{ interpretant: 'sun', kind: 'concept', score: 0.8, exactValue: false, segmentOrdinal: 1 }],
  });
  renderPanel({ selectedHotspot: hotspot });
  expect(screen.getByText('reading Ecclesiasticus 43:1 · interpretants: sun')).toBeInTheDocument();
});

it('renders user, ai, reset, and error items by kind', () => {
  const items: ThreadItem[] = [
    { kind: 'user', id: '1', text: 'What does the sun mean?' },
    { kind: 'ai', id: '2', text: 'It signifies vitality.', instructions: [], regionMarkers: {} },
    { kind: 'reset', id: '3', label: 'now reading The Moon' },
    { kind: 'error', id: '4', text: 'Something went wrong.' },
  ];
  renderPanel({ items });
  expect(screen.getByText('What does the sun mean?')).toBeInTheDocument();
  expect(screen.getByText('It signifies vitality.')).toBeInTheDocument();
  expect(screen.getByText('now reading The Moon')).toBeInTheDocument();
  expect(screen.getByText('Something went wrong.')).toBeInTheDocument();
});

it('renders markdown formatting in an ai item as elements, not literal syntax', () => {
  const items: ThreadItem[] = [{ kind: 'ai', id: '1', text: 'This is **bold**.\n\n- first\n- second', instructions: [], regionMarkers: {} }];
  const { container } = render(
    <AgentChatPanel
      items={items}
      isSending={false}
      onSend={vi.fn()}
      onClear={vi.fn()}
      onNavigateRegion={vi.fn()}
      selectedHotspot={null}
      capabilities={CAPABILITIES}
    />,
  );
  expect(container.querySelector('.bubble strong')).toHaveTextContent('bold');
  expect(container.querySelectorAll('.bubble li')).toHaveLength(2);
  expect(screen.queryByText('**bold**', { exact: false })).not.toBeInTheDocument();
});

it('renders HTML-like text in an ai item as inert text, not a live element', () => {
  const items: ThreadItem[] = [{ kind: 'ai', id: '1', text: '<img src=x onerror="window.__pwned = true">', instructions: [], regionMarkers: {} }];
  const { container } = render(
    <AgentChatPanel
      items={items}
      isSending={false}
      onSend={vi.fn()}
      onClear={vi.fn()}
      onNavigateRegion={vi.fn()}
      selectedHotspot={null}
      capabilities={CAPABILITIES}
    />,
  );
  expect(container.querySelector('.bubble img')).not.toBeInTheDocument();
  expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
});

it('renders a marker with a resolved region as a link that navigates on click', async () => {
  const onNavigateRegion = vi.fn();
  const items: ThreadItem[] = [
    { kind: 'ai', id: '1', text: 'Joy recurs [R1].', instructions: [], regionMarkers: { '[R1]': 'src::1-2' } },
  ];
  renderPanel({ items, onNavigateRegion });

  await userEvent.click(screen.getByRole('link', { name: '[R1]' }));

  expect(onNavigateRegion).toHaveBeenCalledWith('src::1-2');
});

it('renders a marker absent from the map as plain text, not a link', () => {
  const items: ThreadItem[] = [{ kind: 'ai', id: '1', text: 'Joy recurs [R9].', instructions: [], regionMarkers: {} }];
  renderPanel({ items });

  expect(screen.queryByRole('link', { name: '[R9]' })).not.toBeInTheDocument();
  expect(screen.getByText('Joy recurs [R9].')).toBeInTheDocument();
});

it('renders the same marker at each of its occurrences as an independent link', async () => {
  const onNavigateRegion = vi.fn();
  const items: ThreadItem[] = [
    {
      kind: 'ai',
      id: '1',
      text: 'Joy recurs [R1], and again [R1].',
      instructions: [],
      regionMarkers: { '[R1]': 'src::1-2' },
    },
  ];
  renderPanel({ items, onNavigateRegion });

  const links = screen.getAllByRole('link', { name: '[R1]' });
  expect(links).toHaveLength(2);
  await userEvent.click(links[1]);
  expect(onNavigateRegion).toHaveBeenCalledWith('src::1-2');
});

it('/clear wipes the composer, calls onClear, and never calls onSend or appears as a message', async () => {
  const onSend = vi.fn();
  const onClear = vi.fn();
  renderPanel({ onSend, onClear });
  const input = screen.getByPlaceholderText('Ask about this hotspot…');
  await userEvent.type(input, '/clear{enter}');
  expect(onClear).toHaveBeenCalledTimes(1);
  expect(onSend).not.toHaveBeenCalled();
  expect(screen.queryByText('/clear')).not.toBeInTheDocument();
});

it('sends a trimmed message via onSend and clears the composer', async () => {
  const onSend = vi.fn();
  renderPanel({ onSend });
  const input = screen.getByPlaceholderText('Ask about this hotspot…') as HTMLInputElement;
  await userEvent.type(input, '  hello  {enter}');
  expect(onSend).toHaveBeenCalledWith('hello');
  expect(input.value).toBe('');
});

it('disables the composer input and send button while sending', () => {
  renderPanel({ isSending: true });
  expect(screen.getByPlaceholderText('Ask about this hotspot…')).toBeDisabled();
});

it('disables the send button when the input is empty', () => {
  renderPanel();
  const input = screen.getByPlaceholderText('Ask about this hotspot…');
  const sendButton = input.closest('form')!.querySelector('button[type="submit"]')!;
  expect(sendButton).toBeDisabled();
});

it('toggles collapsed state via the collapse button', async () => {
  const { container } = render(
    <AgentChatPanel
      items={[]}
      isSending={false}
      onSend={vi.fn()}
      onClear={vi.fn()}
      onNavigateRegion={vi.fn()}
      selectedHotspot={null}
      capabilities={CAPABILITIES}
    />,
  );
  expect(container.querySelector('.agent-dock')).not.toHaveClass('collapsed');
  await userEvent.click(screen.getByLabelText('Collapse agent panel'));
  expect(container.querySelector('.agent-dock')).toHaveClass('collapsed');
});

it('/clear is still handled locally when the capabilities document is unavailable', async () => {
  const onSend = vi.fn();
  const onClear = vi.fn();
  renderPanel({ onSend, onClear, capabilities: null });
  await userEvent.type(screen.getByPlaceholderText('Ask about this hotspot…'), '/clear{enter}');
  expect(onClear).toHaveBeenCalledTimes(1);
  expect(onSend).not.toHaveBeenCalled();
});

it('sends a server-handled command as an ordinary turn', async () => {
  const onSend = vi.fn();
  const onClear = vi.fn();
  renderPanel({ onSend, onClear });
  await userEvent.type(screen.getByPlaceholderText('Ask about this hotspot…'), '/query laughter{enter}');
  expect(onSend).toHaveBeenCalledWith('/query laughter');
  expect(onClear).not.toHaveBeenCalled();
});

it('lists only listed commands when the composer holds just "/"', async () => {
  renderPanel();
  await userEvent.type(screen.getByPlaceholderText('Ask about this hotspot…'), '/');
  expect(screen.getByText('/clear')).toBeInTheDocument();
  expect(screen.getByText('/query term[:exact|:filter], …')).toBeInTheDocument();
  expect(screen.queryByText('/query-confirm <id>')).not.toBeInTheDocument();
});

it('narrows the list to the typed prefix as the user types', async () => {
  renderPanel();
  await userEvent.type(screen.getByPlaceholderText('Ask about this hotspot…'), '/s');
  expect(screen.getByText('/summarize')).toBeInTheDocument();
  expect(screen.queryByText('/clear')).not.toBeInTheDocument();
});

it('lists nothing when no command matches the typed prefix', async () => {
  renderPanel();
  await userEvent.type(screen.getByPlaceholderText('Ask about this hotspot…'), '/zzz');
  expect(screen.queryByText('Clear this thread')).not.toBeInTheDocument();
});

it('renders the active completion inline as ghost text, outside the message', async () => {
  renderPanel();
  const input = screen.getByPlaceholderText('Ask about this hotspot…');
  await userEvent.type(input, '/s');
  expect(document.querySelector('.ghost')?.textContent).toBe('/summarize');
  expect(input).toHaveValue('/s');
});

it('completes the active command on Tab', async () => {
  renderPanel();
  const input = screen.getByPlaceholderText('Ask about this hotspot…');
  await userEvent.type(input, '/s{Tab}');
  expect(input).toHaveValue('/summarize ');
});

it('moves the active entry with the arrow keys and completes that one', async () => {
  renderPanel();
  const input = screen.getByPlaceholderText('Ask about this hotspot…');
  await userEvent.type(input, '/{ArrowDown}{Tab}');
  expect(input).toHaveValue('/summarize ');
});

it('completes on Enter without sending while the command is partial', async () => {
  const onSend = vi.fn();
  renderPanel({ onSend });
  const input = screen.getByPlaceholderText('Ask about this hotspot…');
  await userEvent.type(input, '/s{enter}');
  expect(input).toHaveValue('/summarize ');
  expect(onSend).not.toHaveBeenCalled();
});

it('sends on Enter once the command is fully typed', async () => {
  const onSend = vi.fn();
  renderPanel({ onSend });
  await userEvent.type(screen.getByPlaceholderText('Ask about this hotspot…'), '/summarize{enter}');
  expect(onSend).toHaveBeenCalledWith('/summarize');
});

it('keeps showing the argument syntax after the command name is complete', async () => {
  renderPanel();
  await userEvent.type(screen.getByPlaceholderText('Ask about this hotspot…'), '/query laughter');
  expect(screen.getByText('/query term[:exact|:filter], …')).toBeInTheDocument();
  expect(screen.queryByText('/clear')).not.toBeInTheDocument();
});

it('offers no completion while arguments are typed — Enter sends, Tab does not rewrite', async () => {
  const onSend = vi.fn();
  renderPanel({ onSend });
  const input = screen.getByPlaceholderText('Ask about this hotspot…');
  await userEvent.type(input, '/query laughter{Tab}');
  expect(input).toHaveValue('/query laughter');
  await userEvent.type(input, '{enter}');
  expect(onSend).toHaveBeenCalledWith('/query laughter');
});

it('stops showing a command that takes no arguments once its name is complete', async () => {
  renderPanel();
  await userEvent.type(screen.getByPlaceholderText('Ask about this hotspot…'), '/summarize ');
  expect(screen.queryByText('/summarize')).not.toBeInTheDocument();
});

it('dismisses the list on Escape, leaving the composed text alone', async () => {
  renderPanel();
  const input = screen.getByPlaceholderText('Ask about this hotspot…');
  await userEvent.type(input, '/s{Escape}');
  expect(input).toHaveValue('/s');
  expect(screen.queryByText('/summarize')).not.toBeInTheDocument();
  expect(document.querySelector('.ghost')).toBeNull();
});

it('offers no command list when the capabilities document is unavailable', async () => {
  renderPanel({ capabilities: null });
  await userEvent.type(screen.getByPlaceholderText('Ask about this hotspot…'), '/');
  expect(screen.queryByText('Clear this thread')).not.toBeInTheDocument();
});

it('the confirm affordance sends the instruction command verbatim', async () => {
  const onSend = vi.fn();
  const items: ThreadItem[] = [
    {
      kind: 'ai',
      id: '1',
      text: 'Parsed query: laughter',
      instructions: [{ type: 'confirm_query', payload: { confirm_command: '/query-confirm 7f3a1c9e' } }],
      regionMarkers: {},
    },
  ];
  renderPanel({ items, onSend });

  await userEvent.click(screen.getByRole('button', { name: 'Run this query' }));

  expect(onSend).toHaveBeenCalledWith('/query-confirm 7f3a1c9e');
});

it('shows no confirm affordance on an ordinary reply', () => {
  const items: ThreadItem[] = [{ kind: 'ai', id: '1', text: 'It signifies vitality.', instructions: [], regionMarkers: {} }];
  renderPanel({ items });
  expect(screen.queryByRole('button', { name: 'Run this query' })).not.toBeInTheDocument();
});

it('the discovery confirm affordance sends the instruction command verbatim', async () => {
  const onSend = vi.fn();
  const items: ThreadItem[] = [
    {
      kind: 'ai',
      id: '1',
      text: 'Parsed discovery: where joy is',
      instructions: [
        {
          type: 'confirm_augment',
          payload: { discovery_id: '7f3a1c', confirm_command: '/augment-confirm 7f3a1c' },
        },
      ],
      regionMarkers: {},
    },
  ];
  renderPanel({ items, onSend });

  await userEvent.click(screen.getByRole('button', { name: 'Run this augmentation' }));

  expect(onSend).toHaveBeenCalledWith('/augment-confirm 7f3a1c');
});

it('labels each confirmation chip by its own instruction type', () => {
  const items: ThreadItem[] = [
    {
      kind: 'ai',
      id: '1',
      text: 'Two things to confirm',
      instructions: [
        { type: 'confirm_query', payload: { confirm_command: '/query-confirm aaa' } },
        { type: 'confirm_augment', payload: { confirm_command: '/augment-confirm bbb' } },
      ],
      regionMarkers: {},
    },
  ];
  renderPanel({ items });

  expect(screen.getByRole('button', { name: 'Run this query' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Run this augmentation' })).toBeInTheDocument();
});

it('renders no chip for an instruction type this build does not know', () => {
  const items: ThreadItem[] = [
    {
      kind: 'ai',
      id: '1',
      text: 'Something new',
      instructions: [{ type: 'confirm_something_else', payload: { confirm_command: '/whatever 1' } }],
      regionMarkers: {},
    },
  ];
  renderPanel({ items });

  expect(screen.queryByRole('button', { name: /^Run this/ })).not.toBeInTheDocument();
});
