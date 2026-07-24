import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HotspotCard } from './HotspotCard';
import { makeHotspot } from '../test/fixtures';

it('renders title, convergence badge, and source', () => {
  const hotspot = makeHotspot({ locator: 'Ecclesiasticus 43:1', convergenceCount: 2, source: { ...makeHotspot().source, citation_label: 'Eccl.' } });
  render(<HotspotCard hotspot={hotspot} isActive={false} onSelect={vi.fn()} />);
  expect(screen.getByText('Ecclesiasticus 43:1')).toBeInTheDocument();
  expect(screen.getByText('2 interpretants')).toBeInTheDocument();
  expect(screen.getByText('Eccl.')).toBeInTheDocument();
});

it('renders one chip per match, exact matches labeled distinctly from scored ones', () => {
  const hotspot = makeHotspot({
    matches: [
      { interpretant: 'sun', kind: 'concept', score: 0.812, exactValue: false, segmentOrdinal: 1 },
      { interpretant: '100', kind: 'exact', score: 1, exactValue: true, segmentOrdinal: 1 },
    ],
  });
  render(<HotspotCard hotspot={hotspot} isActive={false} onSelect={vi.fn()} />);
  expect(screen.getByText('sun · 0.81')).toBeInTheDocument();
  expect(screen.getByText('100 · exact')).toBeInTheDocument();
});

it('applies the active class when isActive', () => {
  const hotspot = makeHotspot();
  render(<HotspotCard hotspot={hotspot} isActive onSelect={vi.fn()} />);
  expect(screen.getByRole('button')).toHaveClass('active');
});

it('calls onSelect when clicked', async () => {
  const onSelect = vi.fn();
  render(<HotspotCard hotspot={makeHotspot()} isActive={false} onSelect={onSelect} />);
  await userEvent.click(screen.getByRole('button'));
  expect(onSelect).toHaveBeenCalledTimes(1);
});
