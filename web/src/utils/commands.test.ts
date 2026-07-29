// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import { argHintFor, completionOf, matchCommands } from './commands';
import type { CommandSpec } from '../api/types';

const COMMANDS: CommandSpec[] = [
  { name: '/clear', args: null, summary: 'Clear this thread', handledBy: 'client', listed: true },
  { name: '/summarize', args: null, summary: 'Summarize this region', handledBy: 'server', listed: true },
  { name: '/query', args: 'term[:exact|:filter], …', summary: 'Search on your own terms', handledBy: 'server', listed: true },
  { name: '/query-confirm', args: '<id>', summary: 'Run a parsed ad-hoc query', handledBy: 'server', listed: false },
];

const names = (text: string) => matchCommands(text, COMMANDS).map((command) => command.name);

it('lists every listed command for a bare slash, in declared order', () => {
  expect(names('/')).toEqual(['/clear', '/summarize', '/query']);
});

it('narrows to commands sharing the typed prefix', () => {
  expect(names('/s')).toEqual(['/summarize']);
  expect(names('/q')).toEqual(['/query']);
});

it('matches case-insensitively', () => {
  expect(names('/S')).toEqual(['/summarize']);
});

it('never offers an unlisted command, even typed in full', () => {
  expect(names('/query-confirm')).toEqual([]);
});

it('offers nothing without a leading slash or once an argument begins', () => {
  expect(names('summarize')).toEqual([]);
  expect(names('/query laughter')).toEqual([]);
  expect(names('/summarize ')).toEqual([]);
});

it('offers nothing when no command matches', () => {
  expect(names('/zzz')).toEqual([]);
});

const hint = (text: string) => argHintFor(text, COMMANDS)?.name ?? null;

it('keeps hinting a command that takes arguments while they are typed', () => {
  expect(hint('/query ')).toBe('/query');
  expect(hint('/query laughter, hundred:exact')).toBe('/query');
});

it('hints nothing for a command that declares no arguments', () => {
  expect(hint('/summarize ')).toBeNull();
  expect(hint('/clear ')).toBeNull();
});

it('hints nothing before the command name is finished, or for an unlisted or unknown command', () => {
  expect(hint('/query')).toBeNull();
  expect(hint('/query-confirm 7f3a')).toBeNull();
  expect(hint('/zzz args')).toBeNull();
  expect(hint('tell me about laughter')).toBeNull();
});

it('completes the remainder of the declared name', () => {
  expect(completionOf('/s', COMMANDS[1])).toBe('ummarize');
});

it('completes from the declared casing, not the typed casing', () => {
  expect(completionOf('/SUM', COMMANDS[1])).toBe('marize');
});

it('has no remainder for a fully typed command, a longer text, or no active command', () => {
  expect(completionOf('/summarize', COMMANDS[1])).toBe('');
  expect(completionOf('/summarizes', COMMANDS[1])).toBe('');
  expect(completionOf('/s', undefined)).toBe('');
});
