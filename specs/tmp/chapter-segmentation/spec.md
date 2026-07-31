# Chapter-aware paragraph segmentation

Extends [Ingestion + segmentation](../../retrieval/corpus.md).

## Problem

`data/corpus/` holds four newly added sources — Frazer's *The Golden Bough*,
Weston's *From Ritual to Romance*, Tylor's *Primitive Culture*, and Hall's *The
Secret Teachings of All Ages* — none of which is ingestable under any existing
segmentation scheme:

- `scripture_verse` and `numbered_section` both require every paragraph to
  carry its own leading numeric marker. None of the four sources number
  paragraphs; their only declared structure is chapter-level.
- `paragraph` accepts unnumbered prose but produces no locator at all, so a
  retrieved segment from a 45- or 69-chapter work cannot be cited by chapter.
- Two of the four sources additionally contain an inconsistent sub-chapter
  layer that appears under only some chapters and uses a different convention
  in each source: numbered subsections (*The Golden Bough*) versus unnumbered,
  capitalized topic headings (*The Secret Teachings of All Ages*).
- In one of the four sources, *From Ritual to Romance*, the exact
  chapter-heading text (e.g. `CHAPTER I`, unindented) also occurs elsewhere in
  the same file for non-structural reasons — once as a table-of-contents
  listing, and a second time as headers within a back-of-book endnotes
  section organized by chapter. A chapter-boundary detector that treats every
  occurrence of the heading text as a new chapter start misattributes that
  non-narrative text as chapter content. (*Primitive Culture* also has a
  table of contents whose entries share the same wording as its real chapter
  headings, but distinguishes them typographically — the real headings are
  centered/indented, the table-of-contents ones are not — so no collision
  occurs there.)

`chapter_section` also introduces a workflow none of the three existing
schemes needed: a curator writing and tuning a source-declared pattern
against real text (FR-CO-09/FR-CO-10), rather than picking one of three
fixed, already-correct schemes. Two gaps follow directly from that:

- The document loader's existing idempotency check (FR-CO-04) computes a
  source's content hash from its raw `.txt` bytes alone. A source's declared
  structure (its `scheme`, and, for `chapter_section`, its
  `chapter_pattern`/`subsection_pattern`/boundary fields) is not part of
  that hash. Editing only a source's `structure:` block — the exact thing a
  curator does while tuning a pattern — therefore leaves the recorded
  content hash unchanged, so the loader treats the source as up to date and
  never re-segments it: the vector store silently keeps the segments the
  *previous* pattern produced.
- There is no way to see what a candidate pattern actually produces —
  detected chapter count, labels, segment distribution — without running a
  real ingest (embedding every segment, writing to the graph and vector
  stores). The existing `--dry-run` flag only reports whether a source's
  hash is new/changed/unchanged; it never calls the segmenter.

## Goals

- A segmentation scheme for a source whose only declared structure is
  chapters of unnumbered prose paragraphs, usable by all four sources above
  without further hand-editing of their staged text.
- Each source declares its own chapter-heading pattern (and, where present,
  its own subsection-heading pattern), consistent with the existing principle
  that structure is source-declared, not hardcoded by the engine
  ([corpus.md](../../retrieval/corpus.md) FR-CO-05).
- A segment produced under this scheme carries a locator identifying the
  chapter it falls within, and, when the source declares a subsection
  pattern, the subsection within that chapter.
- Non-structural repeats of chapter-heading text elsewhere in a source (a
  table of contents, a per-chapter endnotes section, or similar) never
  produce spurious chapter boundaries or misattributed segments.
- A source's recorded content hash (FR-CO-04) reflects its declared
  structure as well as its raw text, so tuning a pattern is never silently
  ignored by the idempotency check.
- A candidate structure declaration can be validated against a source's real
  text — and its resulting segment count and locators inspected — without
  requiring an embedding model or writing anything to the graph or vector
  store.

## Non-Goals

- Automatic or inferred structure detection (e.g. topic-shift or ML-based
  chapter boundary detection). Boundaries are recognized only from a pattern
  the source itself declares.
- Changing the segmentation scheme, locator format, or ingested content of
  any existing source (`en_drb`, `en_bahir`).
- Further cleanup of the four sources' staged `.txt` files beyond what is
  already staged under `data/corpus/symbolism/`.
- Deciding domain, citation label, or other bibliographic metadata for the
  four sources — covered separately when each source's `.yaml` is authored.
- Automated detection of a likely-wrong pattern (e.g. flagging a suspicious
  chapter count or an outlier segment distribution). The preview surfaces
  the raw structural result for a curator to judge; it does not judge it.

## Functional Requirements

- FR-CO-08: The document loader supports a `chapter_section` segmentation
  scheme, for a source whose declared structure is chapter-level only, with
  no per-paragraph numbering. Under this scheme, the atomic segment is a
  single paragraph, taken verbatim, as in the `paragraph` scheme (FR-CO-05).
- FR-CO-09: A source declaring the `chapter_section` scheme declares its own
  chapter-heading pattern. A paragraph matching that pattern is a chapter
  heading, not a content segment, and marks the start of a new chapter;
  every following paragraph belongs to that chapter until the next
  chapter-heading match. A chapter-heading paragraph produces no segment of
  its own, the same treatment `numbered_section` (FR-CO-05) already gives a
  paragraph that carries no section marker.
- FR-CO-10: A source declaring the `chapter_section` scheme may additionally
  declare a subsection-heading pattern. Where declared, a paragraph matching
  that pattern marks the start of a new subsection within the current
  chapter and, like a chapter heading, produces no segment of its own; a
  chapter containing no subsection-heading match is treated as one implicit
  subsection spanning the whole chapter. A source that declares no
  subsection pattern has no subsection level at all.
- FR-CO-11: A source declaring the `chapter_section` scheme may declare a
  start and/or end boundary bracketing the region of the file containing its
  real chapters. Paragraphs outside a declared boundary are excluded from
  segmentation. This lets a source exclude front matter (e.g. a table of
  contents whose entries reuse chapter-heading text) and back matter (e.g. an
  endnotes section organized by repeated chapter headers, a bibliography, an
  index) from being read as chapter content.
- FR-CO-12: Each segment produced under the `chapter_section` scheme carries,
  as its structural coordinates (FR-CO-06), the chapter it falls within and,
  when the source declares a subsection pattern, the subsection within that
  chapter — sufficient to render a human-readable locator and to determine
  contiguity with neighboring segments, consistent with every other
  segmentation scheme.
- FR-CO-13 (widens FR-CO-04): A source's content hash is computed from both
  its raw text file's bytes and its declared `structure` block (`scheme`
  and any scheme-specific fields). Changing only the `structure` block, with
  the raw text file unchanged, is detected as a change: the loader treats
  it identically to a raw-text edit — the source's previously ingested
  segments are replaced, never left stale alongside a declaration that no
  longer describes them.
- FR-CO-14: The document loader offers a preview mode that, for a corpus
  source pair, runs its declared segmentation scheme against its actual
  text and reports the resulting segments' structural coordinates (for
  `chapter_section`: each detected chapter/subsection label and how many
  segments fall under it) without embedding any segment or writing to the
  graph or vector store, and without requiring a reachable embedding model.

## Reference sources

`data/corpus/symbolism/en_goldenbough/`, `en_ritualromance/`,
`en_primculture/`, and `en_secretteachings/` each stage one book's plain text
(Gutenberg or, for `en_secretteachings`, sacred-texts.com via the Wayback
Machine) with Gutenberg/site boilerplate already stripped, and no `.yaml`
yet — each is a `chapter_section` candidate per this spec. `en_goldenbough`
and `en_secretteachings` additionally exercise the optional subsection
pattern (FR-CO-10); `en_ritualromance` exercises the front/back-matter
boundary exclusion (FR-CO-11).
