import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HotspotList } from './HotspotList';
import { makeHotspot } from '../test/fixtures';

it('shows the "no query yet" empty state when hasResult is false', () => {
  render(<HotspotList headerText="Hotspots" hasResult={false} hotspots={[]} selectedRegionId={null} onSelect={vi.fn()} />);
  expect(screen.getByText('No query yet')).toBeInTheDocument();
});

it('shows the "no matches" empty state when hasResult is true but hotspots is empty', () => {
  render(<HotspotList headerText="Hotspots" hasResult hotspots={[]} selectedRegionId={null} onSelect={vi.fn()} />);
  expect(screen.getByText('No matches')).toBeInTheDocument();
});

it('renders the header and one card per hotspot when populated', () => {
  const hotspots = [makeHotspot({ regionId: 'r1' }), makeHotspot({ regionId: 'r2', locator: 'Ecclesiasticus 43:2' })];
  render(<HotspotList headerText="Hotspots header" hasResult hotspots={hotspots} selectedRegionId="r1" onSelect={vi.fn()} />);
  expect(screen.getByText('Hotspots header')).toBeInTheDocument();
  expect(screen.getAllByRole('button')).toHaveLength(2);
});

it('marks the selected hotspot active and calls onSelect with its regionId', async () => {
  const onSelect = vi.fn();
  const hotspots = [makeHotspot({ regionId: 'r1', locator: 'A' }), makeHotspot({ regionId: 'r2', locator: 'B' })];
  render(<HotspotList headerText="h" hasResult hotspots={hotspots} selectedRegionId="r1" onSelect={onSelect} />);

  const buttons = screen.getAllByRole('button');
  expect(buttons[0]).toHaveClass('active');
  expect(buttons[1]).not.toHaveClass('active');

  await userEvent.click(buttons[1]);
  expect(onSelect).toHaveBeenCalledWith('r2');
});
