# Mythrix Engine

**An explainable symbolic-interpretation engine — every conclusion traces back to a cited primary source, never a generated guess.**

Most "AI symbol interpreter" tools fall into one of two camps: opaque divinatory black boxes with no reasoning trail, or LLM wrappers that hallucinate plausible-sounding meanings. Mythrix takes a third path — a domain-agnostic knowledge graph of symbols, cross-referenced against a real document corpus through a deterministic, code-driven retrieval pipeline. The LLM never decides what a result *is*; it only orchestrates tool calls and composes cited evidence into conversation. Everything runs **locally** — no hosted API dependency, no data leaving your machine.

Built end-to-end as a solo project: data model, retrieval engine, ranking algorithm, HTTP API, React frontend, and a tool-calling conversational agent.

## What it does

Query a symbol — say, the Tower card in Rider-Waite tarot — and get back **ranked, cited evidence**, not a paragraph of invented meaning:

- **Graph facts** — the sign's properties, interpretants, and cross-domain correspondences (e.g. the Tower's Hebrew-letter correspondence via a Golden Dawn attribution), pulled from a structured knowledge graph.
- **Concept & concept-pair retrieval** — each of the symbol's interpretants (`"fire"`, `"falling figures"`, `"lightning"`...) independently retrieves matching passages from an unrelated reference corpus (the Douay-Rheims Bible, Sefer HaBahir), and passages hit by *multiple* interpretants surface as their own ranked convergence groups.
- **Ranked hotspots** — contiguous passages scored by a specificity-weighted convergence formula (rarer surface forms weigh more), so a passage matched by three distinct concepts outranks one matched by a single common word — with full verbatim text and exact citation, never just a locator.
- **A grounded chat agent** — a docked panel where a local model answers questions *about* a result by calling the same read-only tools the API exposes (symbol lookup, region query, segment fetch, summarize) — never asserting a fact absent from a tool result, with the tool trace shown for every turn.

The reference dataset proves this is genuinely domain-agnostic: all 22 tarot Major Arcana, all 22 Hebrew letters (Sepher Yetzirah correspondences), cross-linked to each other, both read *through* an entirely unrelated corpus (Biblical and Kabbalistic texts) to demonstrate that retrieval works on any curated document set, not just tarot-specific writing.

## Architecture

```
┌──────────-───┐     ┌──────────────────────────┐     ┌────────────────────┐
│ CLI (Typer)  │     │  Backend API (FastAPI)   │     │ Web viewer (React) │
└──────┬───────┘     └────────────┬─────────────┘     └─────────┬──────────┘
       │                          │                             │
       └───────────-───┬──────────┴─────────────────────────────┘
                       │
              ┌────────▼──────────--┐
              │   Core library      │   deterministic retrieval & ranking —
              │  (retrieval, graph, │   no model in the decision path
              │  synthesis, loaders)│
              └────────┬─────────--─┘
                       │
         ┌─────────────┼────────────--──┐
         │                              │
   ┌─────▼───-───┐              ┌───────▼────────┐
   │ Kuzu graph  │              │ Chroma vector  │
   │(Sign Graph) │              │ store (corpus) │
   └──────────-──┘              └────────────────┘

              ┌────────────────────────────┐
              │  Conversational agent      │  local Ollama model,
              │  (tool-calling loop)       │  read-only tools only,
              │  served by the backend API │  citation-validated
              └────────────────────────────┘
```

- **Sign Graph** ([Kuzu](https://kuzudb.com)) — signs, traditions, tradition-scoped manifestations, interpretants, and typed, attributable cross-domain correspondences. No domain-specific field is baked into the schema — enforced by an automated lint check, not convention.
- **Document corpus** ([Chroma](https://www.trychroma.com)) — source documents segmented along their *own* declared structure (verse, numbered section) rather than fixed-size windows, so a citation always resolves to a real structural unit.
- **Retrieval** — two matching channels (dense embedding similarity + exact-token containment), matched live per interpretant at query time — no precomputed match matrix, so editing the graph changes results on the very next query.
- **Ranking** — regions scored by summed, specificity-weighted match strength (a from-scratch lexical-IDF scheme, deliberately not BM25 — see [ADR-002](specs/architecture-decisions/adr-002-dense-plus-exact-token-no-bm25.md) and [ADR-004](specs/architecture-decisions/adr-004-absolute-floor-and-lexical-specificity-ranking.md) for why).
- **Agent** — a bounded tool-calling loop over a fixed, read-only tool set; retrieval stays deterministic even when a model is in the orchestration loop ([ADR-006](specs/architecture-decisions/adr-006-conversational-agent-orchestration-boundary.md)).

Full rationale for every non-obvious call — why no BM25, why live matching over precomputation, why Chroma over a hosted vector DB — is written up in [`specs/architecture-decisions/`](specs/architecture-decisions/).

## Tech stack

| Layer | Tech |
|---|---|
| Core / retrieval | Python 3.12, LangChain, LangGraph |
| Graph store | Kuzu |
| Vector store | Chroma |
| Local LLM runtime | Ollama (embedding + generation, fully offline) |
| API | FastAPI |
| CLI | Typer |
| Frontend | React 19, TypeScript, Vite |
| Testing | pytest, Vitest + React Testing Library |

## Try it

```bash
cd api && uv sync
# install Ollama, pull nomic-embed-text — see docs/SETUP.md for the full walkthrough
cd ..

uv run --project api mythrix load-symbols data --json
uv run --project api mythrix load-documents data/corpus/scripture/en_drb/douay-rheims-bible.txt \
  --tradition douay-rheims --source-slug douay-rheims-bible --json

uv run --project api mythrix query --symbol the-tower --tradition rider-waite
```

Full setup — Ollama models, configuration, and running the API + web viewer together — is in [`docs/SETUP.md`](docs/SETUP.md).

## Docs

The full functional spec is in [`specs/spec.md`](specs/spec.md); the reasoning behind the non-obvious architectural calls is recorded as [ADRs](specs/architecture-decisions/).

## License

AGPL-3.0-or-later — see [LICENSE](LICENSE).
