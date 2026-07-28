import type { CommandSpec } from '../api/types';

// Composer command completion (specs/interfaces/web-viewer.md FR-WEB-18/22/23).
// Pure matching, so the rules are testable without a composer around them.

/** Listed commands whose name begins with `text`, case-insensitively, in the
 * order the backend declared them. Empty unless `text` is still a command name
 * being typed: leading `/`, no whitespace yet. */
export function matchCommands(text: string, commands: CommandSpec[]): CommandSpec[] {
  if (!text.startsWith('/') || /\s/.test(text)) return [];
  const typed = text.toLowerCase();
  return commands.filter((command) => command.listed && command.name.toLowerCase().startsWith(typed));
}

/** The listed command the composed text is now writing arguments for, or `null`.
 * Only commands that declare an argument syntax qualify — there is nothing left
 * to show for one that takes none (FR-WEB-24). Unlike `matchCommands`, this
 * holds *after* the name is complete, so the syntax stays visible while the
 * arguments are typed. */
export function argHintFor(text: string, commands: CommandSpec[]): CommandSpec | null {
  const head = /^(\/\S+)\s/.exec(text)?.[1].toLowerCase();
  if (!head) return null;
  return commands.find((command) => command.listed && command.args !== null && command.name.toLowerCase() === head) ?? null;
}

/** The characters of `command.name` beyond what has been typed, or `''` when the
 * name does not properly extend `text` — which is what distinguishes a
 * fully typed command from one still being completed. Taken from the declared
 * name, not the typed text, so accepting always yields the declared casing. */
export function completionOf(text: string, command: CommandSpec | undefined): string {
  if (!command) return '';
  if (command.name.length <= text.length) return '';
  if (!command.name.toLowerCase().startsWith(text.toLowerCase())) return '';
  return command.name.slice(text.length);
}
