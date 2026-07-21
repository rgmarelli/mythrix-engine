# Architecture Decision Records

This folder records **why** the retrieval architecture is the way it is. It is the
counterpart to the specs under `specs/*/spec.md`: a spec states *what the system
does* and is kept strictly factual (no rationale, alternatives, or test results,
per `CLAUDE.md`); an ADR captures the *reasoning, alternatives, and evidence*
behind a decision, so the factual specs can stay clean while the thinking is not
lost.

Each record uses a lightweight Nygard-style format: **Context → Decision →
Consequences → Alternatives considered**. Records are immutable once accepted; a
changed decision is a new ADR that supersedes an earlier one, not an edit.

| ADR | Decision | Status |
|-----|----------|--------|
| [0001](0001-structural-segmentation-and-region-rollup.md) | Segment along the source's own structure (verse/section); detect convergence by rolling up contiguous segments into a region | Accepted |
| [0002](0002-dense-plus-exact-token-no-bm25.md) | Two matching channels — dense embedding similarity and exact-token containment; no BM25 / no rank-fusion | Accepted |
| [0003](0003-live-per-interpretant-matching-no-precompute.md) | Match each interpretant live at query time; never precompute an interpretant→segment match matrix | Accepted |
| [0004](0004-absolute-floor-and-lexical-specificity-ranking.md) | Rank by lexical-IDF-weighted score over raw, floor-gated match strength; isolated matches are first-class | Accepted |
| [0005](0005-vector-store-chroma-and-lexical-store-path.md) | Keep local Chroma for the vector channel; identify `sqlite-vec`+FTS5 as the migration path if the lexical/df and verse-scale needs outgrow it | Accepted |

Primary sources for these records: `specs/convergence-rollup-retrieval/spec.md`
(the factual requirements these decisions produced) and the empirical benchmarks
run against the live Douay-Rheims and Sefer HaBahir corpora (July 2026).
