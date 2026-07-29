// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ComponentProps } from 'react';
import { SignTraditionPicker } from './SignTraditionPicker';
import { makeSignSummary, makeTradition } from '../test/fixtures';

const signs = [
  makeSignSummary({ slug: 'the-sun', canonical_name: 'The Sun', semiotic_system: 'tarot', tradition_slugs: ['rider-waite'] }),
  makeSignSummary({ slug: 'the-moon', canonical_name: 'The Moon', semiotic_system: 'tarot', tradition_slugs: ['rider-waite', 'thoth'] }),
  makeSignSummary({ slug: 'samekh', canonical_name: 'Samekh', semiotic_system: 'hebrew_alef_bet', tradition_slugs: ['golden-dawn'] }),
];
const traditions = [
  makeTradition({ slug: 'rider-waite', name: 'Rider-Waite' }),
  makeTradition({ slug: 'thoth', name: 'Thoth' }),
  makeTradition({ slug: 'golden-dawn', name: 'Golden Dawn' }),
];

function renderPicker(overrides: Partial<ComponentProps<typeof SignTraditionPicker>> = {}) {
  const props: ComponentProps<typeof SignTraditionPicker> = {
    signs,
    traditions,
    selectedSystem: '',
    selectedSign: '',
    selectedTradition: '',
    minScore: null,
    minScoreDefault: 0.6,
    isStreaming: false,
    onSystemChange: vi.fn(),
    onSignChange: vi.fn(),
    onTraditionChange: vi.fn(),
    onMinScoreChange: vi.fn(),
    onSubmit: vi.fn(),
    ...overrides,
  };
  render(<SignTraditionPicker {...props} />);
  return props;
}

it('scopes the sign dropdown to the selected semiotic system', () => {
  renderPicker({ selectedSystem: 'tarot' });
  const signSelect = screen.getByLabelText('Sign');
  expect(signSelect).toBeEnabled();
  const options = Array.from(signSelect.querySelectorAll('option')).map((o) => o.textContent);
  expect(options).toContain('The Sun');
  expect(options).toContain('The Moon');
  expect(options).not.toContain('Samekh');
});

it('disables the sign dropdown until a system is selected', () => {
  renderPicker();
  expect(screen.getByLabelText('Sign')).toBeDisabled();
});

it('scopes the tradition dropdown to the selected sign\'s tradition_slugs', () => {
  renderPicker({ selectedSystem: 'tarot', selectedSign: 'the-moon' });
  const traditionSelect = screen.getByLabelText('Tradition');
  expect(traditionSelect).toBeEnabled();
  const options = Array.from(traditionSelect.querySelectorAll('option')).map((o) => o.textContent);
  expect(options).toContain('Rider-Waite');
  expect(options).toContain('Thoth');
  expect(options).not.toContain('Golden Dawn');
});

it('resets sign and tradition when the system changes', async () => {
  const props = renderPicker({ selectedSystem: 'tarot' });
  await userEvent.selectOptions(screen.getByLabelText('Semiotic system'), 'hebrew_alef_bet');
  expect(props.onSystemChange).toHaveBeenCalledWith('hebrew_alef_bet');
  expect(props.onSignChange).toHaveBeenCalledWith('');
  expect(props.onTraditionChange).toHaveBeenCalledWith('');
});

it('resets tradition when the sign changes', async () => {
  const props = renderPicker({ selectedSystem: 'tarot' });
  await userEvent.selectOptions(screen.getByLabelText('Sign'), 'the-moon');
  expect(props.onSignChange).toHaveBeenCalledWith('the-moon');
  expect(props.onTraditionChange).toHaveBeenCalledWith('');
});

it('disables submit until both sign and tradition are chosen', () => {
  renderPicker({ selectedSystem: 'tarot', selectedSign: 'the-sun', selectedTradition: '' });
  expect(screen.getByRole('button', { name: 'Explore' })).toBeDisabled();
});

it('enables submit once sign and tradition are chosen, and calls onSubmit without a page reload', async () => {
  const onSubmit = vi.fn();
  renderPicker({ selectedSystem: 'tarot', selectedSign: 'the-sun', selectedTradition: 'rider-waite', onSubmit });
  const button = screen.getByRole('button', { name: 'Explore' });
  expect(button).toBeEnabled();
  await userEvent.click(button);
  expect(onSubmit).toHaveBeenCalledTimes(1);
});

it('shows "Querying…" and disables submit while streaming', () => {
  renderPicker({ selectedSystem: 'tarot', selectedSign: 'the-sun', selectedTradition: 'rider-waite', isStreaming: true });
  const button = screen.getByRole('button', { name: 'Querying…' });
  expect(button).toBeDisabled();
});

it('sends null minScore when the input is cleared, else the parsed number', async () => {
  const onMinScoreChange = vi.fn();
  renderPicker({ onMinScoreChange, minScore: 0.5 });
  const input = screen.getByLabelText('Min score');
  await userEvent.clear(input);
  expect(onMinScoreChange).toHaveBeenCalledWith(null);
});
