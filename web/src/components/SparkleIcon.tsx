// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

/** Marks generated analysis, wherever it appears (specs/interfaces/augmentation.md
 * FR-AU-27, FR-AU-28) — one glyph shared by the rail's card mark and the
 * reader's block header, so the two cannot drift apart. */
export function SparkleIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3l1.6 4.9L18.5 9.4l-4.9 1.6L12 15.9l-1.6-4.9L5.5 9.4l4.9-1.6L12 3Z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
      <path d="M19 15.5l.75 2.15L22 18.4l-2.25.75L19 21.3l-.75-2.15L16 18.4l2.25-.75L19 15.5Z" fill="currentColor" />
    </svg>
  );
}
