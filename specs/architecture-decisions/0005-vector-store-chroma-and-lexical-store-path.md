# ADR 0005 — Keep local Chroma; identify sqlite-vec+FTS5 as the lexical/scale path

- **Status**: Accepted
- **Date**: 2026-07-21
- **Realized by**: `specs/convergence-rollup-retrieval/spec.md` Non-goals (local store)

## Context

The current stack:

| Layer | Technology |
|-------|------------|
| Vector store | **chromadb 1.5.9**, local `PersistentClient`, HNSW cosine |
| Graph | **kuzu 0.11.3** (Sign/Manifestation/interpretant model) |
| Embeddings | **Ollama `nomic-embed-text`** (via `langchain-ollama`) |
| API / UI | **FastAPI + uvicorn** / **React + Vite** |

Constraint: retrieval must run against a **local** store (no hosted/distributed
backend), and the corpus is expected to become **large** (it is small today only
because documents are not uploaded yet).

The retrieval model needs three things from storage:

1. **Dense ANN search** per interpretant — Chroma `query()` does this natively.
2. **Word-bounded token containment** — Chroma local supports `where_document`
   with `$contains` and `$regex`; `$regex \bfifty\b` gives the whole-word match
   [ADR 0002](0002-dense-plus-exact-token-no-bm25.md) requires. The store today
   uses `$contains` (substring) and must move to `$regex`.
3. **Document-frequency counts** for specificity IDF
   [ADR 0004](0004-absolute-floor-and-lexical-specificity-ranking.md) — Chroma has
   **no term statistics**; counting "how many units contain `hundred`" means a
   `$regex` scan per token, cheap at 200 sections, painful at millions.

BM25 is a non-goal [ADR 0002](0002-dense-plus-exact-token-no-bm25.md), so Chroma's
"BM25/`search()` is cloud-only" limitation does **not** block us — this is what
keeps Chroma viable.

## Decision

**Keep local Chroma for the vector channel to build this spec.** It satisfies
needs (1) and (2) with only a `$contains`→`$regex` change; no migration is required
to start. Keep Kuzu, Ollama, and FastAPI/React unchanged — this work touches none
of them structurally.

**Treat two questions as an explicit plan-time spike, not an assumption:**

- Does local Chroma hold at **verse granularity over a huge corpus** (millions of
  vectors; HNSW recall/latency degrade past the low millions)?
- How do we get **document-frequency counts cheaply** without a per-query full
  regex scan (e.g. a df table built at ingest — allowed under
  [ADR 0003](0003-live-per-interpretant-matching-no-precompute.md), which bans
  match precompute, not corpus statistics)?

**Identify the migration target *now* so the decision is deliberate if the spike
fails:** a store with native full-text, which solves the lexical *and* scale halves
in one engine rather than swapping one vector DB for another:

- **`sqlite-vec` + FTS5 — preferred.** Fully embedded (single file, matches the
  local/no-server ethos). FTS5 provides word-bounded matching **and** native
  document-frequency counts; `sqlite-vec` provides the vectors. Unifies dense +
  containment + df + storage.
- **pgvector / Postgres — most capable, heaviest.** `tsvector` + `ts_stat` for df,
  pgvector for ANN, but it is a server to run.
- **LanceDB / Qdrant-local — rejected for this purpose.** They scale vectors better
  than Chroma but have **no** native FTS/df, so they fix scale and leave the
  lexical half unsolved.

## Consequences

- No premature migration: the spec is buildable on today's stack with a one-line
  filter change.
- The genuinely open architectural question is narrowed to **one** thing — the
  lexical+scale store — with a preferred answer already on record.
- If the spike passes, Chroma stays and a small ingest-time df table covers IDF. If
  it fails, `sqlite-vec`+FTS5 is the deliberate destination, not an emergency swap.
- Choosing an FTS-capable store later would also *simplify* the codebase (dense +
  lexical + df in one engine instead of Chroma + a side df index).

## Alternatives considered

- **Migrate to pgvector now.** Rejected: introduces a server dependency before the
  scale need is demonstrated.
- **Cloud Chroma for native BM25/hybrid.** Rejected: violates the local-store
  constraint, and BM25 is a non-goal anyway.
- **Swap Chroma for LanceDB/Qdrant.** Rejected: solves only scale, not the
  lexical/df need that is the actual pressure.
