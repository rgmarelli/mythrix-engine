# ADR-020 — Source-declared chapter-heading patterns, not inferred boundaries

- **Status**: Accepted; extended by [ADR-021](adr-021-locator-normalization-at-query-time.md)
- **Date**: 2026-07-30
- **Realized by**: [specs/retrieval/corpus.md](../retrieval/corpus.md) FR-CO-08–FR-CO-12

## Context

Four newly staged corpus sources — Frazer's *The Golden Bough*, Weston's
*From Ritual to Romance*, Tylor's *Primitive Culture*, Hall's *The Secret
Teachings of All Ages* — are chaptered prose with no per-paragraph structural
marker. Their only declared structure is chapter-level, and each source uses
a different, incompatible heading typography (roman-numeral-dot-title;
`CHAPTER <roman numeral>` with the title on the next line, indented in one
source and not in another; a Title-Case heading inherited from the original
per-chapter HTML page). None of them matches the one heading shape the
engine already recognizes (`chunking._CHAPTER_HEADING`, `"<Title> Chapter
<N>"`, used today for the Bible's chapter locator and the fixed-size
chunker's best-effort one).

Direct inspection of the four staged texts (not assumption) turned up three
distinct, source-specific ways a generic "detect the chapter heading" rule
would go wrong if it tried to work automatically, without a source telling
it what to look for:

- *From Ritual to Romance*'s exact heading text (`CHAPTER I` …
  `CHAPTER XIV`) repeats three times in the file for non-structural
  reasons: once as a table of contents, once for the real chapters, and
  once more as headers in a back-of-book endnotes section organized by
  chapter.
- *The Golden Bough*'s body prose itself contains text that coincidentally
  matches its own chapter-heading shape — a Frazer-authored inline
  enumerated list (`I. In regard to the first head...`) and a citation to an
  author's initials (`L. von Schrenck and his companions...`) — producing
  false positives with no relation to the table of contents or endnotes.
- *The Secret Teachings of All Ages* has three distinct real chapters
  sharing the exact same heading text ("The Ancient Mysteries and Secret
  Societies", Parts I–III), so heading text alone is not even a reliable
  boundary *identifier*, let alone a reliable boundary *detector*.

Each of these is a different failure mode, arising from each book's own
typography and prose, not a single pattern a universal heuristic could
learn once and apply everywhere. [ADR-001](adr-001-structural-segmentation-and-region-rollup.md)
already established the same principle one layer up, for region boundaries:
"Topic/semantic segmentation... rejected as a non-goal... deterministic and
auditable beats learned boundaries here." This decision applies that same
reasoning to chapter-boundary detection itself.

## Decision

A `chapter_section` source declares its own chapter-heading pattern (and,
optionally, a subsection-heading pattern and front/back-matter occurrence-
index boundaries) in its own `.yaml`, rather than the engine inferring
chapter boundaries automatically from generic structural, typographic, or
statistical cues. This extends the project's existing "structure is
source-declared, not engine-assumed" principle ([corpus.md](../retrieval/corpus.md)
FR-CO-05, which already lets a source pick its own segmentation *scheme*)
one level deeper, to the boundary-detection *pattern* within the
`chapter_section` scheme itself.

## Consequences

- A wrong chapter boundary is a wrong, inspectable regex a curator wrote —
  traceable and fixable — not an opaque inference the engine made. Matches
  the auditability bar ADR-001 already set for region boundaries.
- The mechanism doesn't need to special-case which of the three failure
  modes above is at play in a given source: a table-of-contents collision,
  an in-prose false positive, and non-unique heading text are all handled
  the same way, by the curator writing a pattern (and, where needed, an
  occurrence-index boundary) precise enough for that specific source.
- Cost: per-source curator effort. Someone has to read the raw text, write
  and tune the pattern, and validate the resulting chapter count against the
  source's own table of contents — not automatic, and not free. (Already
  reflected as a concrete task in `plan.md`'s Risks for *The Golden Bough*'s
  known false positives.)
- Cost: the occurrence-index boundary fields are positional, not
  content-addressed — an unrelated future hand-edit to a source's `.txt`
  that happens to add or remove an earlier pattern match silently shifts
  what a declared occurrence index points at (already recorded in
  `plan.md`'s Risks; no mitigation proposed there beyond curator review).
- Scoped to the new `chapter_section` scheme only; `scripture_verse`,
  `numbered_section`, and `paragraph` are unaffected and keep their current,
  engine-fixed matching rules.

## Alternatives considered

- **Automatic/inferred chapter-boundary detection** (e.g. generic
  whitespace/typography heuristics, or a statistical/topic-shift detector).
  Rejected for the same reason ADR-001 rejected inferred region boundaries:
  non-auditable, and the four staged sources demonstrate three genuinely
  different ambiguities a single inferred rule would have to arbitrate
  silently, with no way for a curator to see or correct a wrong call short
  of re-deriving the whole heuristic.
- **Growing the engine's one hardcoded heading regex** (`chunking._CHAPTER_HEADING`)
  with more built-in shapes as each new source needs one. Rejected: every
  source examined so far needs a genuinely different shape, so this is
  exactly the "layer additional conditionals... on top of it" pattern
  `CLAUDE.md`'s engineering guidance warns against — the segmenter would
  grow a permanent, unbounded special case per source's specific
  typography, coupling engine code to individual books' formatting.
- **Pre-editing each source's `.txt` to normalize its headings into the one
  shape the engine already recognizes.** Rejected: this was the shortcut
  originally considered for *The Golden Bough* alone before the other three
  sources were staged. It trades a one-time editing pass for a permanent
  data-fidelity compromise (the ingested text stops being a verbatim
  transcription of the source) and cannot express a source with a genuine
  two-level chapter+subsection structure, which the single canonical
  heading shape has no room for.
