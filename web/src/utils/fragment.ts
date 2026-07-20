import type { Fragment } from '../api/types';

export function fragmentTitle(fragment: Fragment): string {
  return fragment.locator || fragment.source.citation_label || fragment.source.title;
}

export function convergenceLabel(count: number): string {
  return `${count} interpretant${count === 1 ? '' : 's'}`;
}
