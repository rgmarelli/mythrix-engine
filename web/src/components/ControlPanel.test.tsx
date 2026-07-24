import { render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { ControlPanel } from './ControlPanel';

function baseProps(): ComponentProps<typeof ControlPanel> {
  return {
    signs: [],
    traditions: [],
    selectedSystem: '',
    selectedSymbol: '',
    selectedTradition: '',
    minScore: null,
    minScoreDefault: 0.6,
    isStreaming: false,
    onSystemChange: vi.fn(),
    onSymbolChange: vi.fn(),
    onTraditionChange: vi.fn(),
    onMinScoreChange: vi.fn(),
    onSubmit: vi.fn(),
    loadError: null,
    queryError: null,
    hasResult: false,
    sourceOptions: [],
    sourceAllCount: 0,
    selectedSourceId: null,
    onSelectSourceId: vi.fn(),
    interpretantOptions: [],
    interpretantAllCount: 0,
    selectedInterpretant: null,
    onSelectInterpretant: vi.fn(),
    interpretantSearch: '',
    onInterpretantSearchChange: vi.fn(),
    open: true,
  };
}

function renderPanel(overrides: Partial<ComponentProps<typeof ControlPanel>> = {}) {
  render(<ControlPanel {...baseProps()} {...overrides} />);
}

it('does not render facet rows when there is no result', () => {
  renderPanel({ hasResult: false });
  expect(screen.queryByText('Sources')).not.toBeInTheDocument();
  expect(screen.queryByText('Interpretants')).not.toBeInTheDocument();
});

it('renders both facet rows once a result exists', () => {
  renderPanel({ hasResult: true });
  expect(screen.getByText('Sources')).toBeInTheDocument();
  expect(screen.getByText('Interpretants')).toBeInTheDocument();
});

it('renders the load error when present', () => {
  renderPanel({ loadError: 'Failed to load signs.' });
  expect(screen.getByText('Failed to load signs.')).toBeInTheDocument();
});

it('renders the query error when present', () => {
  renderPanel({ queryError: 'Sign not found.' });
  expect(screen.getByText('Sign not found.')).toBeInTheDocument();
});

it('applies the open class to the aside element based on the open prop', () => {
  const { container, rerender } = render(<ControlPanel {...baseProps()} open={false} />);
  expect(container.querySelector('aside')).not.toHaveClass('open');
  rerender(<ControlPanel {...baseProps()} open={true} />);
  expect(container.querySelector('aside')).toHaveClass('open');
});
