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
| [ADR-004](adr-004-absolute-floor-and-lexical-specificity-ranking.md) | Rank by lexical-IDF-weighted score over raw, floor-gated match strength; isolated matches are first-class | Accepted; "isolated match" clause narrowed for the `"filter"` directive by [ADR-017](adr-017-filter-directive-requires-convergence.md) |
| [ADR-005](adr-005-vector-store-chroma-and-lexical-store-path.md) | Keep local Chroma for the vector channel; identify `sqlite-vec`+FTS5 as the migration path if the lexical/df and verse-scale needs outgrow it | Accepted |
| [ADR-006](adr-006-conversational-agent-orchestration-boundary.md) | A local generation model may orchestrate Mythrix via read-only tools (converse, select tools), but the retrieval it drives stays deterministic, embedding-only, and cited | Accepted |
| [ADR-007](adr-007-rrf-fusion-and-geometric-mean-pair-scoring.md) | Merge a concept's own queries by Reciprocal Rank Fusion, never raw score; disable the intersemiotic target's bare-name query; score concept-pairs by geometric mean | Accepted; pair scoring superseded by [ADR-013](adr-013-region-rollup-sole-query-shape.md) |
| [ADR-008](adr-008-retrieval-tuning-defaults.md) | `retrieval_match_pool_size=100` and `retrieval_min_score=0.6`, calibrated against a real corpus sweep rather than derived from a formula | Accepted |
| [ADR-009](adr-009-minimal-agent-system-prompt.md) | Keep the agent's system prompt minimal for the local tool-calling model; enforce formatting and cross-turn state in code/UI, not prompt prose | Accepted |
| [ADR-010](adr-010-agnostic-adhoc-interpretant-query.md) | A scoped, deterministically-gated exception letting one separate, explicitly-marked query path build query text from raw user-typed terms, without touching graph-native retrieval/ranking or the agent's model | Accepted |
| [ADR-011](adr-011-backend-declared-agent-capabilities.md) | One backend-served capabilities document declares the command vocabulary and how each instruction type is executed (method, path, body mode, result kind); consumers implement result kinds, not instruction types | Accepted |
| [ADR-012](adr-012-deterministic-command-nodes-bypass-tool-selection.md) | A command whose tool sequence is fully determined by context is handled by a dedicated graph node that calls tools directly, in code; the model is invoked only for a step that is genuinely generative | Accepted |
| [ADR-013](adr-013-region-rollup-sole-query-shape.md) | Region rollup is the only aggregation the retrieval pipeline exposes; per-concept and concept-pair results are retired, superseding ADR-007's geometric-mean pair scoring | Accepted; kind-agnostic eligibility narrowed for the `"filter"` directive by [ADR-017](adr-017-filter-directive-requires-convergence.md) |
| [ADR-014](adr-014-slug-as-agent-entity-identity.md) | The slug is the only entity identity across the agent boundary — context fields and tool-result identity keys carry slugs, display names travel in separate display keys, and every entity-valued tool argument resolves either form to a slug | Accepted |
| [ADR-015](adr-015-deterministic-augmentation-over-viewer-regions.md) | A deterministic command may take its operand from the consumer's current display, deriving every region attribute from the supplied identity alone, fan out N bounded generation calls over a node-only tool set, and stream the results back within its own turn | Accepted; narrows [ADR-012](adr-012-deterministic-command-nodes-bypass-tool-selection.md) and extends [ADR-011](adr-011-backend-declared-agent-capabilities.md); consolidation-call-count clause narrowed by [ADR-016](adr-016-hierarchical-map-reduce-augmentation-consolidation.md) |
| [ADR-016](adr-016-hierarchical-map-reduce-augmentation-consolidation.md) | Consolidate a run's augmentations hierarchically in batches of a configured size rather than one flat invocation, preserving each region's citation marker verbatim as it moves up the reduce tree | Accepted; narrows [ADR-015](adr-015-deterministic-augmentation-over-viewer-regions.md) |
| [ADR-017](adr-017-filter-directive-requires-convergence.md) | A region matched only by `"filter"`-kind matches is not eligible; `"exact"` keeps its standalone eligibility | Accepted; narrows [ADR-004](adr-004-absolute-floor-and-lexical-specificity-ranking.md) and [ADR-013](adr-013-region-rollup-sole-query-shape.md) |

Primary sources for these records: `specs/retrieval/corpus.md`, `specs/retrieval/retrieval.md`,
and `specs/retrieval/ranking.md` (the factual requirements these decisions produced,
`FR-CO-05`–`FR-CO-07`, `FR-RT-12`–`FR-RT-16`, `FR-RK-01`–`FR-RK-10`) and the empirical
benchmarks run against the live Douay-Rheims and Sefer HaBahir corpora (July 2026).
