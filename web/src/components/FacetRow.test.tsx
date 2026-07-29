// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FacetRow } from './FacetRow';

const options = [
  { id: 'sun', label: 'sun', count: 3 },
  { id: 'moon', label: 'moon', count: 1 },
];

it('renders an All row plus one row per option, with counts', () => {
  render(<FacetRow title="Interpretants" allLabel="All" allCount={4} options={options} selected={null} onSelect={vi.fn()} />);
  expect(screen.getByText('All')).toBeInTheDocument();
  expect(screen.getByText('4')).toBeInTheDocument();
  expect(screen.getByText('sun')).toBeInTheDocument();
  expect(screen.getByText('moon')).toBeInTheDocument();
});

it('marks the selected option active', () => {
  render(<FacetRow title="Interpretants" allLabel="All" allCount={4} options={options} selected="sun" onSelect={vi.fn()} />);
  expect(screen.getByText('sun').closest('button')).toHaveClass('active');
  expect(screen.getByText('moon').closest('button')).not.toHaveClass('active');
});

it('calls onSelect with the option id when clicked', async () => {
  const onSelect = vi.fn();
  render(<FacetRow title="Interpretants" allLabel="All" allCount={4} options={options} selected={null} onSelect={onSelect} />);
  await userEvent.click(screen.getByText('moon'));
  expect(onSelect).toHaveBeenCalledWith('moon');
});

it('calls onSelect with null when the All row is clicked', async () => {
  const onSelect = vi.fn();
  render(<FacetRow title="Interpretants" allLabel="All" allCount={4} options={options} selected="sun" onSelect={onSelect} />);
  await userEvent.click(screen.getByText('All'));
  expect(onSelect).toHaveBeenCalledWith(null);
});

it('omits the search input when search/onSearchChange are not supplied', () => {
  render(<FacetRow title="Sources" allLabel="All sources" allCount={4} options={options} selected={null} onSelect={vi.fn()} />);
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
});

it('renders and wires the search input when search/onSearchChange are supplied', async () => {
  const onSearchChange = vi.fn();
  render(
    <FacetRow
      title="Interpretants"
      allLabel="All"
      allCount={4}
      options={options}
      selected={null}
      onSelect={vi.fn()}
      search=""
      onSearchChange={onSearchChange}
      searchPlaceholder="Filter interpretants…"
    />,
  );
  const input = screen.getByPlaceholderText('Filter interpretants…');
  await userEvent.type(input, 'su');
  expect(onSearchChange).toHaveBeenCalledWith('s');
  expect(onSearchChange).toHaveBeenCalledWith('u');
});
