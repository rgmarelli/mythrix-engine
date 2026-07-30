# Chapter-aware paragraph segmentation — Tasks

Derived from [plan.md](plan.md), realizing [spec.md](spec.md) FR-CO-08–FR-CO-14.
Each task is checked off only once its own verification passes — later tasks
build on earlier ones, so work them in order. Reference each task's ID
(`T1`, `T2`, ...) in the corresponding implementation/test docstrings, per
this project's existing convention (see e.g. `test_segmentation.py`'s `T2`).

- [x] **T1 — Authoring schema + domain model fields.**
  Add `chapter_pattern: str | None = None`, `subsection_pattern: str | None
  = None`, `body_start_occurrence: int = 1`, `body_end_occurrence: int = 0`
  to `StructureBlock` (`sign_schema.py`) and the matching four fields
  (empty-string/zero defaults) to `Source` (`models.py`).
  *Verify*: `test_sign_schema.py`'s existing suite passes unmodified,
  including `test_unknown_field_is_rejected`; extend
  `test_parses_source_file` (or add a sibling test) asserting a `structure:`
  block with all four new fields parses into `SourceBlock`/`StructureBlock`
  correctly, and that a source with none of them still parses (all default).

- [x] **T2 — Kùzu DDL.**
  Add the four columns (`chapter_pattern STRING`, `subsection_pattern
  STRING`, `body_start_occurrence INT64`, `body_end_occurrence INT64`) to
  `CREATE NODE TABLE Source(...)` in `schema.py`.
  *Verify*: `test_graph_schema.py` passes against the pinned `kuzu` version.

- [x] **T3 — Graph store round trip.**
  Extend `KuzuGraphStore.upsert_source`'s Cypher/parameters, `get_source`,
  `_get_source_by_id`, and `_source_from_row` (`store.py`) to carry the four
  new fields, mirroring `structure_scheme`'s existing treatment exactly.
  *Verify*: extend `test_graph_store.py`'s
  `test_source_structure_scheme_round_trips`/
  `test_source_structure_scheme_defaults_to_empty` pattern to cover the four
  new fields (non-default values round-trip; defaults round-trip too).

- [x] **T4 — Document loader plumbing.**
  `_parse_corpus_source` reads the four fields off `parsed.source.structure`
  onto the constructed `Source`; `load_document` passes them into
  `segment_text(...)` alongside `scheme=source.structure_scheme`
  (`document_loader.py`).
  *Verify*: extend `test_document_loader.py`'s
  `test_source_with_a_declared_structure_scheme_routes_through_the_segmenter`
  pattern — a `Source` with the four fields set reaches `segment_text` with
  them intact (a stub/spy on `segment_text` or an inline fixture scheme is
  sufficient; the real `chapter_section` segmenter lands in T5).

- [x] **T5 — `chapter_section` segmenter.**
  Add the four new keyword-only parameters to `segment_text` (`segmentation.py`),
  dispatch `scheme == "chapter_section"` to a new `_segment_chapter_section`,
  and implement the algorithm from plan.md: paragraph-anchored `fullmatch`
  heading/subsection detection, the match-counter + in-body gate for
  `body_start_occurrence`/`body_end_occurrence`, chapter-ordinal tracking
  (for sources with non-unique heading text), and the
  `locator`/`section` split (subsection when declared and matched, else
  chapter alone). Raise a validation error when `chapter_pattern` is empty
  for a `chapter_section` source.
  *Verify*, in `test_segmentation.py`, per plan.md's Testing strategy:
  chapter-only source (no `subsection_pattern`); chapter+subsection source,
  including a chapter with no subsection match falling back to the implicit
  whole-chapter subsection; `body_start_occurrence`/`body_end_occurrence`
  excluding a ToC-shaped repeat before and an endnotes-shaped repeat after
  (mirrors *From Ritual to Romance*'s real shape); non-unique heading text
  across two chapters still producing distinct locators via the chapter
  ordinal; missing/empty `chapter_pattern` raises. Also confirm every
  existing `scripture_verse`/`numbered_section`/`paragraph` test in this
  file still passes unmodified — the four new parameters must be true
  no-ops for them.

- [x] **T6 — Content-hash widening (FR-CO-13).**
  Add `_structure_signature(source) -> str` and widen `_hash_content` to
  accept it (`document_loader.py`); update both call sites —
  `load_document`'s hash comparison and `load_corpus_directory`'s `dry_run`
  hash comparison — to pass `_structure_signature(source)`.
  *Verify*: a new test asserting two otherwise-identical sources with
  different `chapter_pattern` hash differently, and identical
  text+structure hashes the same; a `load_corpus_directory` round-trip test
  where only a fixture source's structure fields change between two runs
  (text untouched) — dry-run reports `"changed"`, and a real run deletes
  and replaces that source's chunks (`vector_store.delete_by_source` is
  called) rather than no-op'ing.

- [x] **T7 — Segmentation preview (FR-CO-14).**
  Extend `load_corpus_directory`'s `dry_run` branch to also call
  `segment_text(...)` and fold a structural summary (total segment count,
  and for `chapter_section`, ordered `(chapter label, segment count)`
  pairs) into each source's result dict; extend `load_documents.py`'s
  dry-run output formatting to print it.
  *Verify*: a `chapter_section` fixture's dry-run result includes the
  expected chapter count and per-chapter segment counts; a
  `scripture_verse`/`numbered_section`/`paragraph` fixture's dry-run result
  still includes a plain total segment count with no per-chapter
  breakdown; dry-run still constructs no embedder/vector store (existing
  fixtures already assert `vector_store=None, embedder=None` for dry-run
  calls — confirm this still holds).

- [x] **T8 — Full regression pass.**
  Run the complete existing test suite plus lint/format.
  *Verify*: `pytest` (full `api/tests/` suite, not just the files touched
  above), `ruff check .`, `ruff format --check .` all pass — confirms
  `en_drb`/`en_bahir` and every other existing consumer of `Source`/
  `segment_text`/the document loader is unaffected.

- [x] **T9 — Author the four corpus sources' `.yaml` files.**
  Starting from the drafted examples under
  `specs/tmp/chapter-segmentation/examples/`, write the real
  `data/corpus/symbolism/en_goldenbough/golden-bough.yaml`,
  `en_ritualromance/from-ritual-to-romance.yaml`,
  `en_primculture/primitive-culture.yaml`, and
  `en_secretteachings/secret-teachings-of-all-ages.yaml` — filling in
  bibliographic metadata (deferred by spec.md's Non-Goals until now:
  `citation_label`, `license`, `uri`, `description`) and a validated
  `structure:` block for each.
  *Verify*, using T7's preview (`mythrix load-documents --dry-run` against
  `data/corpus/symbolism/`): each source's detected chapter count matches
  its own table of contents — 69 for Golden Bough (I–LXIX; specifically
  re-check the known false-positive count from plan.md, tightening
  `chapter_pattern` until it reads exactly 69, not 72), 14 for *From Ritual
  to Romance*, 19 for *Primitive Culture*, and the resolved count for
  *The Secret Teachings of All Ages* (45 chapters, plus Preface/
  Introduction if the open inclusion decision from plan.md is resolved in
  favor of including them) — with no unexpected outlier chapters (e.g. a
  suspiciously short one-paragraph "chapter") in the preview output.

- [x] **T10 — Real ingestion + spot-check.**
  Run `mythrix load-documents` (no `--dry-run`) against
  `data/corpus/symbolism/` for the four sources.
  *Verify*: reported chunks-written counts match T9's preview segment
  counts; query the running system for at least one chapter+subsection
  citation (Golden Bough) and one chapter-only citation (*From Ritual to
  Romance* or *Primitive Culture*) and confirm the rendered locator/section
  matches the source's real structure (e.g. a Golden Bough result cites a
  specific chapter *and* subsection, not just a bare paragraph).
