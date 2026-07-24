import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ComponentProps } from 'react';
import { AgentChatPanel } from './AgentChatPanel';
import { makeHotspot } from '../test/fixtures';
import type { ThreadItem } from '../state/useTabs';

function renderPanel(overrides: Partial<ComponentProps<typeof AgentChatPanel>> = {}) {
  const props: ComponentProps<typeof AgentChatPanel> = {
    items: [],
    isSending: false,
    onSend: vi.fn(),
    onClear: vi.fn(),
    selectedHotspot: null,
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
    { kind: 'ai', id: '2', text: 'It signifies vitality.', cards: [] },
    { kind: 'reset', id: '3', label: 'now reading The Moon' },
    { kind: 'error', id: '4', text: 'Something went wrong.' },
  ];
  renderPanel({ items });
  expect(screen.getByText('What does the sun mean?')).toBeInTheDocument();
  expect(screen.getByText('It signifies vitality.')).toBeInTheDocument();
  expect(screen.getByText('now reading The Moon')).toBeInTheDocument();
  expect(screen.getByText('Something went wrong.')).toBeInTheDocument();
});

it('renders citation and interpretant_chips cards on an ai item', () => {
  const items: ThreadItem[] = [
    {
      kind: 'ai',
      id: '1',
      text: 'Here is the passage.',
      cards: [
        { type: 'citation', sourceLabel: 'Eccl.', locator: '43:1', text: 'the pride of the height' },
        { type: 'interpretant_chips', chips: [{ interpretant: 'sun', kind: 'concept', score: 0.8, segmentOrdinal: 1 }] },
      ],
    },
  ];
  renderPanel({ items });
  expect(screen.getByText('"the pride of the height"', { exact: false })).toBeInTheDocument();
  expect(screen.getByText('sun · 0.80')).toBeInTheDocument();
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
  const { container } = render(<AgentChatPanel items={[]} isSending={false} onSend={vi.fn()} onClear={vi.fn()} selectedHotspot={null} />);
  expect(container.querySelector('.agent-dock')).not.toHaveClass('collapsed');
  await userEvent.click(screen.getByLabelText('Collapse agent panel'));
  expect(container.querySelector('.agent-dock')).toHaveClass('collapsed');
});
