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
| [ADR-001](adr-001-structural-segmentation-and-region-rollup.md) | Segment along the source's own structure (verse/section); detect convergence by rolling up contiguous segments into a region | Accepted |
| [ADR-002](adr-002-dense-plus-exact-token-no-bm25.md) | Two matching channels — dense embedding similarity and exact-token containment; no BM25 / no rank-fusion | Accepted |
| [ADR-003](adr-003-live-per-interpretant-matching-no-precompute.md) | Match each interpretant live at query time; never precompute an interpretant→segment match matrix | Accepted |
| [ADR-004](adr-004-absolute-floor-and-lexical-specificity-ranking.md) | Rank by lexical-IDF-weighted score over raw, floor-gated match strength; isolated matches are first-class | Accepted |
| [ADR-005](adr-005-vector-store-chroma-and-lexical-store-path.md) | Keep local Chroma for the vector channel; identify `sqlite-vec`+FTS5 as the migration path if the lexical/df and verse-scale needs outgrow it | Accepted |
| [ADR-006](adr-006-conversational-agent-orchestration-boundary.md) | A local generation model may orchestrate Mythrix via read-only tools (converse, select tools), but the retrieval it drives stays deterministic, embedding-only, and cited | Accepted |
| [ADR-007](adr-007-rrf-fusion-and-geometric-mean-pair-scoring.md) | Merge a concept's own queries by Reciprocal Rank Fusion, never raw score; disable the intersemiotic target's bare-name query; score concept-pairs by geometric mean | Accepted |
| [ADR-008](adr-008-retrieval-tuning-defaults.md) | `retrieval_match_pool_size=100` and `retrieval_min_score=0.6`, calibrated against a real corpus sweep rather than derived from a formula | Accepted |

Primary sources for these records: `specs/retrieval/corpus.md`, `specs/retrieval/retrieval.md`,
and `specs/retrieval/ranking.md` (the factual requirements these decisions produced,
`FR-CO-05`–`FR-CO-07`, `FR-RT-12`–`FR-RT-16`, `FR-RK-01`–`FR-RK-10`) and the empirical
benchmarks run against the live Douay-Rheims and Sefer HaBahir corpora (July 2026).
