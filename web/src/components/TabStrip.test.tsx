// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TabStrip } from './TabStrip';
import { makeSignSummary } from '../test/fixtures';
import type { Tab } from '../state/useTabs';

function makeTab(overrides: Partial<Tab> = {}): Tab {
  return {
    id: 'tab-1',
    selectedSystem: '',
    selectedSign: '',
    selectedTradition: '',
    minScore: null,
    queryResult: null,
    isQuerying: false,
    queryError: null,
    selectedSourceId: null,
    selectedInterpretant: null,
    selectedRegionId: null,
    interpretantSearch: '',
    augmentations: {},
    hotspotSearch: '',
    agentSessionId: 'session-1',
    agentItems: [],
    agentSending: false,
    extendedRegions: {},
    ...overrides,
  };
}

it('labels a tab with no query result as "New query"', () => {
  const tabs = [makeTab()];
  render(<TabStrip tabs={tabs} activeTabId="tab-1" signs={[]} onSelect={vi.fn()} onClose={vi.fn()} onAdd={vi.fn()} />);
  expect(screen.getByText('New query')).toBeInTheDocument();
});

it('labels a queried tab with the resolved sign name', () => {
  const signs = [makeSignSummary({ slug: 'the-sun', canonical_name: 'The Sun' })];
  const tabs = [makeTab({ selectedSign: 'the-sun', queryResult: { facets: { sources: [], interpretants: [] }, hotspots: [] } })];
  render(<TabStrip tabs={tabs} activeTabId="tab-1" signs={signs} onSelect={vi.fn()} onClose={vi.fn()} onAdd={vi.fn()} />);
  expect(screen.getByText('The Sun')).toBeInTheDocument();
});

it('falls back to "Untitled query" when the queried sign is not found in signs', () => {
  const tabs = [makeTab({ selectedSign: 'unknown', queryResult: { facets: { sources: [], interpretants: [] }, hotspots: [] } })];
  render(<TabStrip tabs={tabs} activeTabId="tab-1" signs={[]} onSelect={vi.fn()} onClose={vi.fn()} onAdd={vi.fn()} />);
  expect(screen.getByText('Untitled query')).toBeInTheDocument();
});

it('marks the active tab and calls onSelect for the others', async () => {
  const onSelect = vi.fn();
  const tabs = [makeTab({ id: 'tab-1' }), makeTab({ id: 'tab-2' })];
  render(<TabStrip tabs={tabs} activeTabId="tab-1" signs={[]} onSelect={onSelect} onClose={vi.fn()} onAdd={vi.fn()} />);
  const labels = screen.getAllByText('New query');
  expect(labels[0].closest('.tab')).toHaveClass('active');
  expect(labels[1].closest('.tab')).not.toHaveClass('active');

  await userEvent.click(labels[1]);
  expect(onSelect).toHaveBeenCalledWith('tab-2');
});

it('close button calls onClose without also triggering onSelect', async () => {
  const onSelect = vi.fn();
  const onClose = vi.fn();
  const tabs = [makeTab({ id: 'tab-1' })];
  render(<TabStrip tabs={tabs} activeTabId="tab-1" signs={[]} onSelect={onSelect} onClose={onClose} onAdd={vi.fn()} />);
  await userEvent.click(screen.getByLabelText('Close tab'));
  expect(onClose).toHaveBeenCalledWith('tab-1');
  expect(onSelect).not.toHaveBeenCalled();
});

it('calls onAdd when the new-tab button is clicked', async () => {
  const onAdd = vi.fn();
  render(<TabStrip tabs={[makeTab()]} activeTabId="tab-1" signs={[]} onSelect={vi.fn()} onClose={vi.fn()} onAdd={onAdd} />);
  await userEvent.click(screen.getByLabelText('New tab'));
  expect(onAdd).toHaveBeenCalledTimes(1);
});
