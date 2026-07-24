# Setup

Everything here runs fully local — no hosted API dependency. You need Python,
[`uv`](https://docs.astral.sh/uv/), and a local [Ollama](https://ollama.com)
installation for the embedding/generation steps.

## 1. Install dependencies

```bash
uv sync
```

This installs `mythrix` in editable mode along with all pinned runtime and dev
dependencies (see `pyproject.toml`) — into `uv`'s project virtualenv, not
system-wide. Every `mythrix` command below must be run as `uv run mythrix ...`
(not bare `mythrix ...`), unless you've activated that virtualenv yourself
(`source .venv/bin/activate`).

## 2. Install Ollama and pull models

Install Ollama natively (not via Docker — see below):

```bash
brew install ollama       # macOS, if you have Homebrew
brew services start ollama  # runs the daemon in the background
```

(No Homebrew, or on Linux/Windows? Download the installer from
[ollama.com/download](https://ollama.com/download) instead.)

Then pull the models you'll use:

```bash
ollama pull nomic-embed-text   # embedding model (default)
ollama pull llama3.2           # or any generation model you prefer
```

Confirm the daemon is running: `ollama list` should succeed without error.

**Why not Docker for Ollama:** Docker Desktop on macOS can't pass GPU/Metal
acceleration through to a container, so a containerized Ollama would run
noticeably slower than `ollama serve` on the host for the same models. It also
adds real complexity (image builds, multi-GB model volumes) for no benefit in
a single-user local setup. Worth reconsidering only if this project later
needs the `@pytest.mark.requires_ollama` integration tests to run in CI.

## 3. Configuration

Mythrix reads settings from environment variables (prefix `MYTHRIX_`), a local
`.env` file, or CLI-provided overrides — see `core/config.py` for the full
list and precedence order. The two you'll set most often:

```bash
export MYTHRIX_KUZU_DB_PATH=~/.mythrix/graph.kuzu
export MYTHRIX_CHROMA_PERSIST_DIR=~/.mythrix/chroma
export MYTHRIX_GENERATION_MODEL=llama3.2
```

(`embedding_model` defaults to `nomic-embed-text`; `generation_model` has no
default and must be set explicitly — this is deliberate, since installed
Ollama models vary machine to machine, per `plan.md`'s design.)

## 4. Load the reference dataset

The `data/` directory ships a reference dataset proving the pipeline
end-to-end: all 22 tarot Major Arcana (Rider-Waite tradition, structured from
Waite's *Pictorial Key to the Tarot*), all 22 Hebrew letters (`kabbalah`
domain, Sepher Yetzirah planetary/zodiac/elemental assignments) cross-linked
to their tarot card via `corresponds_to`, and one independent corpus document
(the complete Douay-Rheims Bible, Old and New Testament, public domain) — see
`specs/spec.md`'s "Reference implementation scope"
for why the corpus document is deliberately a different source.

`load-symbols` walks the whole `data/` tree (`root.rglob("symbols/*.yaml")`,
etc.), so one command loads every domain — tarot, kabbalah, and bible's
tradition/source metadata — together:

```bash
uv run mythrix load-symbols data --json

uv run mythrix load-documents data/bible/documents/douay-rheims-bible.txt \
  --tradition douay-rheims --source-slug douay-rheims-bible --json
```

Both commands are idempotent — safe to re-run. The document load embeds the
full Bible text (~5.6MB, ~1700 chunks), so expect this step to take a while
on CPU-only local Ollama embedding.

## 5. Query

```bash
# human-readable: graph facts, per-concept passages, and pair-convergence groups
uv run mythrix query --symbol the-tower --tradition rider-waite

# structured output — full evidentiary chain (FR-RT-06)
uv run mythrix query --symbol the-tower --tradition rider-waite --json

# widen the pool searched for concept-pair convergence (FR-RT-08), independent of --top-k
uv run mythrix query --symbol the-tower --tradition rider-waite --match-pool 50
```

Per FR-RT-10, no generation model is ever invoked on this path — only the
embedding model is needed, so this works with just `nomic-embed-text`
pulled. Expect the `GRAPH FACTS` block (`[G#]`), one `PASSAGES` block per
concept (most likely including a Bible passage from Genesis 11, the Tower
of Babel — the thematic match to "The Tower" — though retrieval is
corpus-wide, so any resonant passage may surface), and a `CANDIDATES`
section per converging concept pair with its combined and component scores.
There is no synthesized narrative and no `--facts-only`/`--strict` flags —
every query already returns this complete evidentiary result.

## Running tests

```bash
uv run pytest tests/unit -q        # fast, no Ollama needed
uv run ruff check .
uv run ruff format --check .
```

`tests/integration/` holds `@pytest.mark.requires_ollama` tests that need a
real running daemon — not part of the default `tests/unit` run:

```bash
uv run pytest tests/integration -m requires_ollama -q
```

This is now a single fast test (`test_synthesis_chain_ollama.py`, one small
`invoke()` call). The full-corpus end-to-end acceptance tests (`the-tower`
query, `the-sun` convergence) were removed — each re-ingested the complete
~1700-chunk Bible on every run, 40+ minutes total, judged not worth
maintaining as routine coverage. See `specs/symbol-interpretation-core/tasks.md`
(T25, T39) and `docs/TODO.md`'s Verification section for the historical
record of what those runs found before removal.
