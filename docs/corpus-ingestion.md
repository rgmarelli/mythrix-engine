# Corpus Ingestion

How to load primary-source documents (scripture, myth, folklore, etc.) into
the vector-searchable corpus, distinct from the curated symbolic graph loaded
by `load-signs`. A corpus document is never assigned a `Tradition` — see
`specs/retrieval/corpus.md` (FR-CO-02) for why.

## Overview

Ingestion reads a directory of `<name>.yaml` + `<name>.txt` pairs, segments
each text according to its own declared structure (or a fixed-size
word-count fallback), embeds the segments with a local Ollama model, and
stores the result in two places:

* **Kuzu** (`~/.mythrix/graph.kuzu` by default) — one `Source` node per
  document (metadata + content hash).
* **Chroma** (`~/.mythrix/chroma` by default) — one embedded vector per
  segment/chunk, in the `mythrix_sources` collection.

All commands run from the repo root via `uv run --project api mythrix ...`
(see `docs/SETUP.md` for environment setup).

## Preparing a source

Every corpus document needs two colocated files under the directory you'll
point ingestion at, sharing the same filename stem:

```
data/corpus/<domain>/<source-id>/<name>.yaml
data/corpus/<domain>/<source-id>/<name>.txt
```

A `.txt` with no matching `.yaml` (or vice versa) is silently skipped, not
an error. `.txt` files are read as UTF-8 — no other encoding or file format
(PDF, DOCX, Markdown, HTML) is supported.

### YAML schema

```yaml
source:
  id: "en_drb"              # required, unique across the whole tree
  domain: scripture          # required — tags chunks in place of a tradition
  title: "..."                # required
  author: "..."                # required
  citation_label: "Douay-Rheims"  # optional, default ""
  publication_year: 1750      # optional
  license: "public-domain"    # optional
  uri: "https://..."           # optional
  description: >               # optional
    ...
  structure:                   # optional — omit for fixed-size chunking
    scheme: scripture_verse
```

`id` is authored explicitly — it is not derived from the filename or
directory. A duplicate `id` anywhere in the discovered tree fails the whole
run before anything is written.

### `structure` (optional)

Omitting `structure` falls back to fixed-size, paragraph-aware word-count
chunking (see `--chunk-size`/`--chunk-overlap` below). Declaring it routes
the text through a structural segmenter instead, producing one segment per
natural unit (verse, numbered section, paragraph, or chapter/subsection)
with a locator (e.g. `Genesis 1:1`, `§12`, `Ch. III`) instead of an
arbitrary chunk boundary. Prefer this whenever the source has a natural
addressable structure.

| `scheme` | Produces one segment per... | Extra fields |
|---|---|---|
| `scripture_verse` | verse (detects `"<chapter>:<verse>. "` markers, e.g. `1:1. In the beginning...`, under a preceding `"<Book> Chapter <N>"` heading) | — |
| `numbered_section` | paragraph starting with `"N. "` | — |
| `paragraph` | paragraph, verbatim | — |
| `chapter_section` | subsection (or whole chapter, if no subsection pattern) | `chapter_pattern` (required), `subsection_pattern` (optional) |

`chapter_section` fields:

* `chapter_pattern` — regex, matched against a whole (whitespace-stripped)
  paragraph to recognize a chapter heading. May include a named group
  `(?P<title>...)`. Required when `scheme: chapter_section`.
* `subsection_pattern` — same kind of match, one level finer than chapter.
  Optional — a source with no sub-chapter structure leaves it unset.
* `body_start_occurrence` / `body_end_occurrence` — 1-indexed positions
  among all `chapter_pattern` matches marking the real first/last chapter,
  so a source can exclude a table of contents or endnotes section that
  reuses the same heading text. Default `1` / `0` (`0` = unbounded, through
  end of file).

Example (`data/corpus/symbolism/en_goldenbough/golden-bough.yaml`):

```yaml
source:
  id: "en_goldenbough"
  domain: symbolism
  citation_label: "Golden Bough"
  structure:
    scheme: chapter_section
    chapter_pattern: "[IVXLCM]+\\. (?P<title>[A-Z][A-Za-z ,'\\-]{2,60})"
    subsection_pattern: "\\d+\\. (?P<title>[A-Z][A-Za-z ,'\\-]{2,60})"
  title: "The Golden Bough: A Study of Magic and Religion (Abridged Edition)"
  author: "Sir James George Frazer"
  publication_year: 1922
  license: "public-domain"
  uri: "https://www.gutenberg.org/ebooks/3623"
```

## Validating before a real ingest

A real ingest embeds every segment with Ollama and is comparatively slow and
costly to redo, so validate first — especially a new `chapter_section`
pattern:

```bash
# 1. No stores, no Ollama — fastest way to eyeball exact locators:
uv run --project api mythrix preview-segments data/corpus

# 2. Opens the graph store (to compare content hashes) but not Ollama —
#    shows segment/chapter counts and whether each source is new/unchanged/changed:
uv run --project api mythrix load-documents data/corpus --dry-run --json
```

## Running ingestion

```bash
uv run --project api mythrix load-documents data/corpus --json
```

This requires a running Ollama daemon with the configured embedding model
pulled (`ollama pull nomic-embed-text` — see `docs/SETUP.md`).

### Options

| Flag | Default | Meaning |
|---|---|---|
| `path` (positional) | — | Directory containing corpus `<name>.yaml`/`<name>.txt` pairs, searched recursively |
| `--chunk-size` | `650` | Words per chunk — only used for sources with no declared `structure` |
| `--chunk-overlap` | `100` | Overlap words between consecutive fixed-size chunks |
| `--dry-run` | `False` | Validate without writing or embedding (see above) |
| `--json` | `False` | Machine-readable output |

### Idempotency

Ingestion is safe to re-run. Each source's `.txt` content plus its declared
`structure` block is hashed; if the hash matches what's already recorded for
that `source.id`, the run is a no-op (`chunks_written: 0`). If it differs,
the source's existing chunks are deleted and replaced — never left stale
alongside new ones. Editing only the `structure` block (e.g. tuning a
`chapter_pattern` regex) is detected as a change even though the `.txt`
bytes didn't move.

### Example output

```bash
$ uv run --project api mythrix load-documents data/corpus
Ingested 1721 chunk(s) for source 'en_drb'.
No changes: 'en_goldenbough' is already up to date.
```

```bash
$ uv run --project api mythrix load-documents data/corpus --dry-run --json
{
  "dry_run": true,
  "results": [
    {
      "source_id": "en_drb",
      "status": "new",
      "detail": "would ingest for the first time",
      "segmentation": {"total_segments": 31103}
    }
  ]
}
```

Expect a large document to take a while on CPU-only local Ollama — the full
Douay-Rheims Bible (~5.6MB) is several thousand chunks.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Error: ...` (validation), exit 1 | Malformed YAML, or a duplicate `source.id` across the tree | Fix the offending file; the path is included in the message |
| `Error: Run 'ollama pull <model>' and try again.` | Embedding model not pulled | `ollama pull <model>` |
| `Error: ...` (other embedding failure) | Ollama unreachable, oversized batch, connection dropped | Check `ollama list` and `MYTHRIX_OLLAMA_BASE_URL` |
| Raw `UnicodeDecodeError` traceback | `.txt` file isn't valid UTF-8 | Re-save the file as UTF-8 |
| Raw `ValueError` traceback about a chapter pattern | `chapter_section` scheme with an empty/missing `chapter_pattern`, or an unrecognized `scheme` name | Fix the `structure` block; verify with `preview-segments` first |
| A source silently doesn't appear in results | `.txt` with no matching `.yaml`, or vice versa | Ensure both files exist with the same stem |
| Retrieval later raises a model-mismatch error | Corpus was ingested with a different `embedding_model` than the one now configured | Re-run `load-documents` with the current embedding model |

## Related documentation

* `specs/retrieval/corpus.md` — functional requirements (FR-CO-01 through
  FR-CO-18) behind this pipeline.
* `specs/architecture-decisions/adr-020-source-declared-chapter-heading-patterns.md`
  — rationale for `chapter_section`.
* `specs/architecture-decisions/adr-021-locator-normalization-at-query-time.md`
  — why locator formatting happens at query time, not ingest.
* `docs/architecture.md` — where the corpus fits relative to the sign graph.
* `docs/SETUP.md` — environment setup and the reference dataset.
