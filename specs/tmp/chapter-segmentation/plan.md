# Chapter-aware paragraph segmentation — Plan

Realizes [spec.md](spec.md) (FR-CO-08–FR-CO-14), extending
[corpus.md](../../retrieval/corpus.md).

## Summary

Add a fourth segmentation scheme, `chapter_section`, alongside the existing
`scripture_verse`, `numbered_section`, and `paragraph`. Unlike those three,
its boundary-detection patterns are not hardcoded — a source declares its own
chapter-heading pattern (and, optionally, a subsection-heading pattern and a
front/back-matter exclusion window) in its own `.yaml`, and the segmenter
reads those patterns as parameters rather than assuming one fixed shape. This
requires plumbing new per-source fields through every layer that currently
carries `structure_scheme` alone: the YAML schema, the `Source` domain model,
the Kùzu graph schema, the graph store's read/write queries, and the document
loader's call into `segment_text`.

Two workflow gaps surfaced by that tunable-pattern workflow are resolved
alongside it: the existing content-hash idempotency check (FR-CO-04) only
covers a source's raw text, so editing only a `structure:` block currently
leaves stale segments in place undetected (FR-CO-13, below); and there is
currently no way to see what a candidate pattern produces without a real,
costly ingest (FR-CO-14, below).

## Data flow (current → extended)

```
source.yaml (structure: {scheme, ...})
  -> sign_schema.StructureBlock          [Pydantic parse — EXTEND]
  -> document_loader._parse_corpus_source [YAML -> Source          — EXTEND]
  -> graph_store.upsert_source            [Source -> Kùzu Source node — EXTEND]
       ...
  -> graph_store.get_source               [Kùzu Source node -> Source — EXTEND]
  -> document_loader.load_document        [Source -> segment_text() call — EXTEND]
  -> segmentation.segment_text(scheme=...) [dispatch — EXTEND: new branch]
       -> segmentation._segment_chapter_section  [NEW]
  -> vector_store.add_chunks              [unchanged — consumes Chunk list]
```

Every other consumer of a `Chunk` (ranking, retrieval, citation rendering) is
unaffected — `chapter_section` produces the same `Chunk` shape
(`index`, `text`, `char_start`, `char_end`, `locator`, `ordinal`, `section`)
the other three schemes already produce.

## Schema and model changes

`StructureBlock` (`api/src/mythrix/core/loaders/sign_schema.py`) currently
has one field, `scheme: str`. Add four optional fields, all defaulting to
"unset" so a `scripture_verse`/`numbered_section`/`paragraph` source's YAML
is unaffected:

| Field | Type | Meaning |
|---|---|---|
| `chapter_pattern` | `str \| None = None` | Required when `scheme: chapter_section`; a regex matched against a whole paragraph (after whitespace-stripping) to recognize a chapter heading. |
| `subsection_pattern` | `str \| None = None` | Optional; same matching rule, one level finer than chapter. |
| `body_start_occurrence` | `int = 1` | 1-indexed: which `chapter_pattern` match (counting from the start of the file) is the real first chapter. Matches before it (e.g. a table of contents reusing the same heading text) are excluded. |
| `body_end_occurrence` | `int = 0` | 1-indexed: which `chapter_pattern` match is the real last chapter. `0` means unbounded (through end of file). Matches after it (e.g. a per-chapter endnotes section) are excluded, along with everything following them. |

These four fields need the same round trip `structure_scheme` already has:

- `Source` (`api/src/mythrix/core/models.py`): add the same four fields
  (empty-string/zero defaults), alongside `structure_scheme`.
- `Source` Kùzu DDL (`api/src/mythrix/core/graph/schema.py`): add four
  columns (`chapter_pattern STRING`, `subsection_pattern STRING`,
  `body_start_occurrence INT64`, `body_end_occurrence INT64`) to the
  `CREATE NODE TABLE Source(...)` block, next to `structure_scheme`.
- `KuzuGraphStore` (`api/src/mythrix/core/graph/store.py`): `upsert_source`'s
  `MERGE`/`ON CREATE SET`/`ON MATCH SET` Cypher and its parameter dict need
  the four new fields; `get_source`, `_get_source_by_id`, and the shared
  `_source_from_row` helper need the four new columns added to their
  `RETURN`/row-unpacking. Mechanical, mirrors the existing
  `structure_scheme` plumbing at each of these call sites exactly.
- `document_loader._parse_corpus_source`: reads the four fields off
  `parsed.source.structure` (when present) onto the constructed `Source`,
  the same way it already reads `.scheme`.
- `document_loader.load_document`: passes the four fields from `source` into
  `segment_text(...)` alongside `scheme=source.structure_scheme`.

**Rollout note:** `KuzuGraphStore._ensure_schema` only runs `create_schema`
when the `Sign` table doesn't exist yet — there is no `ALTER TABLE`/migration
path in this codebase today. Any existing local Kùzu database predating this
change needs to be recreated (delete the `.kuzu` directory and re-run the
structured-data + document loaders) once these columns are added; this is a
one-time local dev-environment step, not a production migration concern at
this project's current stage.

## `segment_text` signature

`api/src/mythrix/core/vector/segmentation.py`'s public entry point gains four
new keyword-only parameters, all optional, ignored by the three existing
schemes:

```
def segment_text(
    text: str,
    *,
    scheme: str,
    chapter_pattern: str | None = None,
    subsection_pattern: str | None = None,
    body_start_occurrence: int = 1,
    body_end_occurrence: int = 0,
) -> list[Chunk]:
```

`scheme == "chapter_section"` dispatches to a new `_segment_chapter_section`,
raising a validation error (a new, specific exception, or reusing
`UnknownSegmentationSchemeError`'s sibling pattern — decide during
implementation) if `chapter_pattern` is empty, since it is the one field this
scheme cannot function without.

## `_segment_chapter_section` algorithm

Reuses `_paragraphs(text)` (already shared by `_segment_scripture_verse` and
`_segment_numbered_section`) rather than `chunking._chapter_headings`'s
whole-text `re.MULTILINE` scan — a heading here is defined as *a paragraph
whose entire (stripped) text matches the pattern*, not a substring found
anywhere, which is what lets a source's own front-matter table of contents
avoid colliding with its body in two of the four reference sources (Golden
Bough's TOC line shape differs from its body's; Primitive Culture's TOC
entries are typographically distinguishable — flush-left — from its
indented/centered body headings) without any special-casing. Confirmed by
direct inspection of the staged texts, not assumed.

Walking `_paragraphs(text)` in order, with `chapter_pattern`/
`subsection_pattern` compiled once and matched via `fullmatch` against each
paragraph's stripped text:

1. Track a **match counter** (how many paragraphs have fullmatched
   `chapter_pattern` so far) and an **in-body** flag, initially `False`.
2. A paragraph that fullmatches `chapter_pattern`: increment the counter.
   - If the counter is now within `[body_start_occurrence, body_end_occurrence
     or +inf]`: this is a real chapter start. Set in-body `True`, record this
     paragraph's text as the current chapter label together with a running
     chapter ordinal (1-indexed count of *real* chapter starts, independent
     of the match counter — needed because heading text is not always
     unique, see Risks), and reset the current subsection to "none".
   - Otherwise (before `body_start_occurrence` or after
     `body_end_occurrence`): this is a non-structural repeat (table of
     contents, endnotes header). Set in-body `False`. Do not update the
     current chapter/subsection.
   - Either way, this paragraph produces no segment of its own (FR-CO-09).
3. A paragraph that fullmatches `subsection_pattern` (only checked when
   `subsection_pattern` is set and in-body is `True`): record it as the
   current subsection label; produces no segment of its own (FR-CO-10).
4. Any other paragraph: if in-body is `True`, it is a content segment —
   `text` is the paragraph verbatim (through `normalize_chunk_text`, as the
   other schemes already do), `locator`/`section` derived from the current
   chapter/subsection state (see below). If in-body is `False`, it is
   excluded (front matter before the first real chapter, or back matter
   after the last).

**`locator`/`section` mapping**, matching the split `_segment_scripture_verse`
already establishes (verse = locator, chapter = section) rather than
inventing a new convention:

- Source declares no `subsection_pattern`, or the current chapter has had no
  subsection match yet: `locator` = `"{chapter ordinal}. {chapter heading
  text}"`, `section` = `""` (chapter is the only level, same as
  `numbered_section`'s "no grouping above itself").
- Source declares `subsection_pattern` and the current chapter has a
  subsection: `locator` = the subsection heading text, `section` =
  `"{chapter ordinal}. {chapter heading text}"`.

The chapter ordinal (not just the heading's own text) is included in the
label because heading text is not guaranteed unique within a source — *The
Secret Teachings of All Ages* has three distinct chapters titled "The Ancient
Mysteries and Secret Societies" (Parts I–III, distinguished only by an `<h2>`
subtitle that the staged plain text does not carry as separately-matchable
structure). Ordinal position still disambiguates them even when their
heading text is identical.

## Content-hash widening (FR-CO-13)

`document_loader._hash_content(content: str) -> str` currently hashes only
the raw `.txt` bytes. Two call sites need the widened input:

- `load_document`: `content_hash = _hash_content(content)`, compared against
  `source.content_hash` to decide no-op vs. replace. By the time
  `load_document` runs, `source` (fetched via `graph_store.get_source`) has
  already been refreshed with the current YAML's structure fields by
  `load_corpus_directory`'s preceding `upsert_source` call — so the current
  declaration is already available at this call site without extra
  plumbing.
- `load_corpus_directory`'s `dry_run` branch: `content_hash =
  _hash_content(txt_path.read_text(...))`, compared against `existing.content_hash`.
  Here `source` is the freshly-parsed-from-YAML object (not yet persisted,
  since dry run writes nothing), so it already carries the candidate
  declaration too.

Both call sites already have a `Source` (or the freshly-parsed equivalent)
in scope carrying `structure_scheme`/`chapter_pattern`/`subsection_pattern`/
`body_start_occurrence`/`body_end_occurrence`. Add a small helper,
`_structure_signature(source) -> str`, joining those five fields in a fixed
order with an unambiguous delimiter, and change `_hash_content` to accept
it (`_hash_content(content, structure_signature="")`), hashing
`content + "\x00" + structure_signature` instead of `content` alone. Both
call sites pass `_structure_signature(source)`; every other caller
(currently none outside these two) keeps the empty default.

**Consequence worth calling out explicitly**: this changes what
`content_hash` *means*, not just what it covers going forward. Every source
already ingested under the old (`.txt`-only) formula — including `en_drb`
and `en_bahir` — has a stored hash that will not match the newly-computed
one on the very next `load-documents` run after this ships, so both will be
detected as "changed" and reingested once, even though neither their text
nor their structure actually changed. This is a one-time, harmless
side effect (re-embeds already-correct content) of shipping a correctness
fix, not a bug — but it should be expected, not discovered.

## Segmentation preview mode (FR-CO-14)

`load_corpus_directory`'s existing `dry_run` branch already avoids
constructing an `embedder`/`vector_store` (the CLI passes `None` for both
when `--dry-run` is set) and already has `source`'s parsed structure fields
in scope — it just currently stops at a hash comparison. Extend it to also
call `segment_text(content, scheme=source.structure_scheme, chapter_pattern=...,
...)` (the same pure call `load_document` makes) and fold a structural
summary into that source's result dict: total segment count, and, for
`chapter_section` specifically, the ordered list of `(chapter label, segment
count)` pairs (from each segment's `.section` or, for a chapter with no
subsections, `.locator`). No embedding, no graph/vector-store writes — pure
text in, structural counts out.

`load_documents.py`'s dry-run output formatting (`run_load_documents`)
prints this summary alongside the existing new/changed/unchanged status;
`--json` already exists and carries the full per-chapter breakdown for a
source with many chapters (e.g. 69, for Golden Bough) without needing a
second output mode — the plain-text path can stay a short summary line
(chapter count, segment count) to stay scannable in a terminal.

This reuses the existing `--dry-run` flag entirely — no new CLI command or
flag, consistent with not adding an abstraction beyond what's needed.

## Per-source declarations (informational — not authored yet)

Deciding the four reference sources' actual `.yaml` bibliographic fields
(`citation_label`, `license`, `uri`, etc.) is explicitly out of scope of this
plan (spec.md Non-Goals) and belongs to a later, separate task. The
`structure:` block each would need, however, is already grounded in direct
inspection of the staged `.txt` files and is recorded here so implementation
has concrete, verified starting patterns rather than needing to redo this
analysis:

- **`en_goldenbough`**: `chapter_pattern` matches a paragraph like `I. The
  King of the Wood` (roman numeral, `.`, title); `subsection_pattern`
  matches `1. Diana and Virbius` (arabic numeral, `.`, title). No boundary
  fields needed — the table of contents uses a different shape (`Chapter
   1. The King of the Wood`) and its subsection listing is indented, so it
  never forms its own paragraph matching `subsection_pattern`. 69 real
  chapters (I–LXIX). **Known false positives to guard against**: the body
  prose itself contains a Frazer-authored inline enumerated list (`I. In
  regard to the first head...`, `II. Passing to...`, `III. Thus far...`) and
  a citation to an author's initials (`L. von Schrenck and his companions...
  `) that both coincidentally fullmatch the roman-numeral chapter shape — a
  naive pattern produces 72 chapter-heading matches against 69 real
  chapters. Tightening `chapter_pattern` (e.g. requiring the matched text to
  end without a following-sentence period, or cross-checking the detected
  chapter count against the table of contents) is implementation work for
  this specific source's YAML, not a segmenter-engine change.
- **`en_ritualromance`**: `chapter_pattern` matches a two-line paragraph,
  `CHAPTER <roman numeral>` followed by a title line (e.g. `CHAPTER I` /
  `Introductory`) — the pattern must account for the embedded newline within
  one paragraph, not just a single line. No subsections. The identical
  heading shape repeats three times in the file: 14 table-of-contents
  entries, 14 real chapters, then a second copy of headers (`CHAPTER II`
  through `CHAPTER XIV`, 13 of them — chapter I has no endnotes) introducing
  a back-of-book endnotes section. `body_start_occurrence = 15` (skip the 14
  ToC matches), `body_end_occurrence = 28` (stop after the 14th real
  chapter, before the endnotes' repeated headers).
- **`en_primculture`**: `chapter_pattern` matches a two-line, indented/
  centered paragraph, `CHAPTER <roman numeral>.` followed by an
  all-capitals title line. No subsections. 19 real chapters (I–XIX,
  continuous across the two source volumes, confirmed by directly comparing
  indentation between the table-of-contents entries — flush-left, 19 of
  them, matching the real count coincidentally — and the real body headings
  — indented). No boundary fields needed, since the pattern's whitespace
  requirement alone excludes the table of contents.
- **`en_secretteachings`**: `chapter_pattern` matches a Title-Case heading
  paragraph (e.g. `The Ancient Mysteries and Secret Societies`); this is the
  original per-chapter HTML page's `<h1>`, now its own plain-text paragraph.
  `subsection_pattern` matches an all-capitals topic heading paragraph (e.g.
  `ANIMALS`) that appears under some chapters, not others. The book's own
  table-of-contents block uses all-capitals chapter titles, which does not
  collide with the Title-Case `chapter_pattern`, so no boundary fields are
  needed. **Open decision, not yet resolved**: the Preface and Introduction
  (each a distinct, substantial essay) precede the first `chapter_pattern`
  match and are excluded by construction (in-body starts `False` and only
  becomes `True` at the first real chapter match) unless `chapter_pattern`
  is deliberately written to also match `PREFACE`/`INTRODUCTION` as their
  own chapter-equivalent entries — a content-inclusion choice for whoever
  authors this source's `.yaml`, not something this plan resolves.

## Testing strategy

Follows the existing pattern in `api/tests/unit/test_segmentation.py` (one
`segment_text(text, scheme=...)` call against a small inline fixture string
per behavior, asserting on `.locator`/`.section`/`.ordinal`/`.text`) — no new
test infrastructure needed:

- Chapter-only source (no `subsection_pattern`): paragraphs group under the
  right `locator`, `section` stays empty, non-heading paragraphs before the
  first chapter are excluded.
- Chapter+subsection source: `section`/`locator` split as specified; a
  chapter with no subsection match falls back to the whole-chapter implicit
  subsection.
- `body_start_occurrence`/`body_end_occurrence`: a fixture text with a
  table-of-contents-shaped repeat of the same heading before the real
  chapters, and an endnotes-shaped repeat after — confirms both are excluded
  and only the real region is segmented (mirrors the *From Ritual to
  Romance* shape directly).
- Missing/empty `chapter_pattern` on a `chapter_section` source raises the
  validation error.
- `document_loader` round-trip test (mirroring
  `api/tests/unit/test_document_loader.py`'s existing style): a `Source`
  with the four new fields set survives `upsert_source` → `get_source`
  unchanged, and `load_document` routes to `segment_text` with them passed
  through — extends that file's existing fixtures rather than adding a new
  one.
- Regression: every existing `scripture_verse`/`numbered_section`/
  `paragraph`/fixed-chunk test continues to pass unmodified, confirming the
  four new optional parameters are true no-ops for the three existing
  schemes.
- `tests/unit/test_graph_schema.py` (already exists, validates DDL against
  the pinned `kuzu` version per that module's own docstring) needs no new
  test, but will exercise the extended `CREATE NODE TABLE Source` DDL as
  part of its existing checks.
- `_structure_signature`/widened `_hash_content` (FR-CO-13): two sources with
  identical text but different `chapter_pattern` hash differently; two
  sources with identical text and identical structure fields hash the same
  regardless of field order internally. `load_corpus_directory` round-trip:
  editing only a fixture source's structure fields (text unchanged) between
  two runs reports `"changed"` in dry-run mode and triggers a real
  delete-and-replace (via `vector_store.delete_by_source`) on a real run —
  the exact scenario that motivated FR-CO-13.
- Preview mode (FR-CO-14): a `chapter_section` fixture source's dry-run
  result includes the expected chapter count and per-chapter segment
  counts; a `scripture_verse`/`numbered_section`/`paragraph` fixture's
  dry-run result still includes a plain total segment count (no per-chapter
  breakdown, since those schemes have no chapter level); dry-run continues
  to pass `vector_store=None, embedder=None` through unchanged — asserts no
  embedding/store call happens by construction (the existing test fixtures
  already pass `None` for both in dry-run tests).

## Risks / open questions

- **False-positive heading matches inside body prose.** Demonstrated
  concretely for Golden Bough (an inline enumerated list and an author-
  initial citation both coincidentally match its chapter-heading shape).
  This is not unique to the new scheme — `numbered_section` has the same
  latent risk for the Bahir — but chapter-level mis-segmentation is more
  visible (it silently starts a new "chapter" mid-book) than a single
  mis-parsed section would be. Mitigation is per-source pattern precision
  plus a validation step (compare detected chapter count to the source's own
  table of contents), not an engine-level guarantee.
- **`body_start_occurrence`/`body_end_occurrence` are match-count positional,
  not content-addressed.** If a source's `.txt` is later hand-edited in a
  way that adds or removes an earlier `chapter_pattern` match (e.g. fixing a
  typo that happened to also fullmatch the pattern), the declared occurrence
  indices silently point at the wrong match rather than failing loudly. A
  possible follow-up (not proposed as part of this plan) is a loader-time
  sanity check that logs the resolved chapter labels for a `chapter_section`
  source so a curator can eyeball them after any edit.
- **Schema growth on `Source`.** Four new columns are specific to one
  segmentation scheme and stay empty for the other three. Considered and
  rejected: a single JSON-encoded `structure_config` column instead of four
  typed columns, which would keep the `Source` table's column count fixed
  regardless of how many schemes exist — rejected as unwarranted for a
  fourth scheme when the project has no concrete fifth scheme in view (KISS;
  see `python-design-patterns` guidance against designing for hypothetical
  future requirements). Revisit if a fifth scheme's needs make the flat-column
  approach unwieldy.
- **No migration path.** Covered above (Rollout note) — accepted as a local
  dev-environment cost at this project's current (pre-production) stage,
  not solved by this plan.
- **One-time reingestion of every existing source on deploy.** Covered above
  (Content-hash widening) — widening what `content_hash` covers means every
  previously-ingested source's stored hash stops matching on the first run
  after this ships, so `en_drb`/`en_bahir` get reingested once even though
  nothing about them changed. Accepted as a one-time, harmless cost of
  fixing FR-CO-04's blind spot, not deferred or hidden.

## Out of scope (restated from spec.md)

No changes to `en_drb`/`en_bahir` behavior; no inferred/ML boundary
detection; no further `.txt` cleanup beyond what is already staged; no
per-source `.yaml` authoring (bibliographic metadata, final pattern
tuning/validation) — that is follow-up implementation work once this plan
and its tasks are agreed.
