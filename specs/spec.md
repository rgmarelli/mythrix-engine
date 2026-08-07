# Mythrix — System Specification

## 1. Problem

Existing symbolic-interpretation tools fall into two unsatisfying categories: opaque divinatory black boxes that offer no reasoning trail, or unstructured LLM wrappers that generate plausible-sounding but invented interpretations. Researchers and practitioners working in comparative symbolism, digital humanities, and related fields need a tool where every conclusion is traceable back to (a) the specific signs identified, (b) the primary sources retrieved, and (c) the reasoning chain connecting them — with interpretive traditions kept distinct rather than blended into one composite "meaning."

## 2. Vision

A domain-agnostic knowledge graph of signs, cross-referenced against real document corpora through a deterministic, code-driven retrieval pipeline, running entirely locally. The LLM never decides what a result *is* — retrieval and ranking are code, not model output — it only orchestrates read-only tool calls and composes cited evidence into conversation, at the layer where generated text is explicitly permitted. Every conclusion traces to a cited primary source, never a generated guess.

## 3. Goals

- A domain-agnostic **Sign Graph** data model representing signs, interpretive traditions, tradition-scoped manifestations, properties, interpretants, and intersemiotic interpretants — see [Domain Model](domain/domain-model.md) and [Structured Data](domain/structured-data.md).
- A **retrieval pipeline** grounded in curated primary-source documents, searched as one independent corpus rather than scoped by interpretive tradition — see [Corpus](retrieval/corpus.md) and [Retrieval](retrieval/retrieval.md).
- A **local-only pipeline** (no hosted API dependency) that returns ranked, cited evidence for a query — retrieved graph facts and source passages — rather than a generated narrative.
- **One core library behind every surface**: a backend HTTP API that answers queries, plus a CLI carrying a structured-data loader that populates the Sign Graph and a document loader that ingests primary source texts into the vector store.
- **Tarot as the first reference dataset**, proving a single-sign, single-tradition query end-to-end through the full pipeline — see [Reference Implementation](#9-reference-implementation).
- **Structural, source-declared segmentation** of corpus documents into atomic segments, rolled up into specificity-weighted, ranked regions — a second retrieval path alongside per-concept/concept-pair retrieval, sharing the same live per-interpretant matching engine — see [Ranking](retrieval/ranking.md).
- **A web viewer over an independent backend HTTP API**, both reusing the core retrieval pipeline and stores with no duplicated logic — see [Backend API](interfaces/api.md) and [Web Viewer](interfaces/web-viewer.md).
- **An in-app conversational agent**, served by the backend API and surfaced as a docked chat panel, operating the existing retrieval pipeline through a fixed set of read-only tools, grounding every claim in a tool result and its citation — see [Conversational Agent](interfaces/agent.md).
- **An in-panel "Add Context" control** that progressively loads verbatim context around a hotspot's matched segments, bounded by the source's own chapter/section structure — see [Context Expansion](retrieval/context-expansion.md).
- **A tabbed workspace** in the web viewer — multiple independent queries held open at once, each with its own facets/result/selected hotspot and its own grounded agent conversation.
- **Region augmentation** — one confirmation-gated command that reads every region the viewer is currently displaying against a free-text question, delivers each reading to the region it describes as it is produced, and consolidates the readings into a single answer citing the regions that support it; the sequence is fixed in code and its generation fan-out is bounded by configuration — see [Region Augmentation](interfaces/augmentation.md).

## 4. Non-Goals

- Multi-sign or spread-style queries (e.g. interpreting several signs together in one request).
- Conversational or free-text natural-language request parsing on the query path — v1 resolves a query from structured parameters only. The conversational agent ([interfaces/agent.md](interfaces/agent.md)) is a separate, additive layer and does not change this, with one narrow, explicitly-scoped exception: the ad-hoc interpretant query path ([interfaces/agnostic-query.md](interfaces/agnostic-query.md), [ADR-010](architecture-decisions/adr-010-agnostic-adhoc-interpretant-query.md)), reachable only via an explicit `/query` command and its matching confirmation command, parsed deterministically rather than by the generation model, and never from incidental conversation. Region augmentation ([interfaces/augmentation.md](interfaces/augmentation.md)) retrieves nothing at all: its free-text focus is an instruction to the generation model only and never reaches the query path.
- Hardening against adversarial input / prompt injection beyond baseline mitigations (data-not-instructions framing, citation-id validation). v1 assumes curator-supplied, not arbitrary, source documents.
- Verifying that LLM paraphrases are faithful to their cited source, beyond the fact-checker's own per-sentence supported/unsupported classification against that turn's evidence ([ADR-025](architecture-decisions/adr-025-post-hoc-fact-checker-replaces-self-citation.md)). Deeper automated faithfulness/entailment checking is future work.
- Concurrent multi-process write access to the graph store or vector store (see [interfaces/api.md](interfaces/api.md) for the specific CLI/API exclusion).

Subsystem-specific non-goals (e.g. no BM25 ranking, no cross-tradition comparison UI, no mutating agent tools) are recorded in each subsystem's own spec under §6.

## 5. System Overview

The sections below describe how the architecture realizes the objectives in
§2–§3: retrieval and ranking are code, never model output, so every result
traces to a cited primary source; the one exception — text generation — is
confined to the agent layer (chat, region augmentation) and is itself bounded
and citation-validated rather than free-running.

### 5.1 Architecture at a Glance

```
┌──────────────┐     ┌──────────────────────────┐     ┌────────────────────┐
│ CLI (loaders)│     │  Backend API (FastAPI)   │     │ Web viewer (React) │
└──────┬───────┘     └────────────┬─────────────┘     └─────────┬──────────┘
       │                          │                             │
       └────-──────────┬──────────┴─────────────────────────────┘
                       │
              ┌────────▼────────────┐
              │   Core library      │   deterministic retrieval & ranking —
              │  (retrieval, graph, │   no model in the decision path
              │  chat, loaders)     │
              └────────┬────────────┘
                       │
         ┌─────────────┴──────────────────┐
         │                                │
   ┌─────▼───────┐              ┌─────────▼──────┐
   │ Kuzu graph  │              │ Chroma vector  │
   │(Sign Graph) │              │ store (corpus) │
   └─────────────┘              └────────────────┘

              ┌───────────────────────────────┐
              │  Conversational agent         │  local Ollama daemon,
              │  (tool-calling loop +         │  read-only tools only,
              │  region augmentation)         │  citation-validated
              │  served by the backend API    │
              └───────────────────────────────┘
```

- **Sign Graph** ([Kuzu](https://kuzudb.com)) — signs, traditions, tradition-scoped manifestations, interpretants, and typed, attributable cross-domain correspondences. No domain-specific field is baked into the schema — enforced by an automated check (§7).
- **Document corpus** ([Chroma](https://www.trychroma.com)) — source documents segmented along their *own* declared structure (verse, numbered section) rather than fixed-size windows, so a citation always resolves to a real structural unit.
- **Retrieval** — two matching channels (dense embedding similarity + exact-token containment), matched live per interpretant at query time — no precomputed match matrix.
- **Ranking** — regions scored by summed, specificity-weighted match strength (a from-scratch lexical-IDF scheme, deliberately not BM25 — [ADR-002](architecture-decisions/adr-002-dense-plus-exact-token-no-bm25.md), [ADR-004](architecture-decisions/adr-004-absolute-floor-and-lexical-specificity-ranking.md)).
- **Agent** — a bounded tool-calling loop over a fixed, read-only tool set; retrieval stays deterministic even when a model is in the orchestration loop ([ADR-006](architecture-decisions/adr-006-conversational-agent-orchestration-boundary.md)).
- **Region augmentation** — a deterministic, code-driven fan-out over the regions a consumer is currently displaying, layered on the agent's chat panel rather than the query path: one generation call reads each region's own verbatim passage against a free-text focus, and the resulting per-region readings are reduced to one answer through **hierarchical map-reduce consolidation** — grouped into bounded batches, consolidated batch by batch, and re-grouped until one result remains — rather than one flat prompt whose synthesis quality degrades as the region count grows. Every citation marker (`[R#]`) is assigned once, at the first (leaf) consolidation level, and carried forward unchanged through every level above it, so the final answer's citations always resolve to a real displayed region regardless of how many consolidation levels produced the text ([ADR-015](architecture-decisions/adr-015-deterministic-augmentation-over-viewer-regions.md), [ADR-016](architecture-decisions/adr-016-hierarchical-map-reduce-augmentation-consolidation.md)).
- **Models** — everything runs against a **local Ollama daemon**; no hosted/cloud model is ever called ([ADR-006](architecture-decisions/adr-006-conversational-agent-orchestration-boundary.md)). Two independent model roles exist: an **embedding model** (`nomic-embed-text` by default), used by both document ingestion and query-time matching so vectors stay comparable, and never involved in retrieval decisions themselves; and a **generation model**, used only by the agent layer (chat turns, region augmentation reads and consolidations) and never by the query path (FR-RT-10). The generation model has no hardcoded default — installed Ollama models vary by machine — so it is explicitly configured per deployment (`MYTHRIX_GENERATION_MODEL`, e.g. `qwen3:1.7b`) and a missing or unreachable model fails with an actionable error rather than silently guessing a fallback.

### 5.2 Core Concepts

- **Sign Graph** — `semiotic_system` (domain), `sign`, `manifestation` (a sign within one tradition), `interpretant` (a meaning token, the source of retrieval query text), `intersemiotic_interpretant` (a typed, attributable cross-sign edge). Full vocabulary: [domain-model.md](domain/domain-model.md).
- **Corpus** — `segment` (the atomic retrieval unit, e.g. one verse), located by `structural coordinates`. Full vocabulary: [corpus.md](retrieval/corpus.md).
- **Ranking** — `region` (a contiguous span of segments), `hotspot` (the web viewer's term for a ranked region), `match floor`, `specificity weight`. Full vocabulary: [ranking.md](retrieval/ranking.md).
- **Context expansion** — `matched segment` vs. `context segment`, `internal gap`, `leading/trailing edge`, `chapter boundary`. Full vocabulary: [context-expansion.md](retrieval/context-expansion.md).
- **Agent** — `agent`, `tool`, `turn`, `session`, `tool trace`, `thread` (an agent session scoped to one hotspot). Full vocabulary: [agent.md](interfaces/agent.md).
- **Region augmentation** — `focus` (the analysis instruction, never query text), `visible regions` (what the consumer is displaying), `augmentation` (one region's reading), `consolidation`, `run`, `turn event`. Full vocabulary: [augmentation.md](interfaces/augmentation.md).
- **Web viewer** — `tab` (an isolated unit of workspace state: selection, facets, result, hotspot, agent thread). Full vocabulary: [web-viewer.md](interfaces/web-viewer.md).

### 5.3 End-to-End Data Flow

Structured data (signs, traditions, manifestations) and primary-source documents are loaded independently into the Sign Graph and vector store respectively (§8.1, §8.2). A query names one sign and tradition; the queried sign's interpretants — plus any reachable across `intersemiotic_interpretants` — are resolved into query text, and each is matched live against the vector store via embedding similarity or exact-token containment. Matches are rolled up into ranked, specificity-weighted regions. The web viewer and the conversational agent both sit on top of the same region-query and segment-fetch operations, adding no retrieval logic of their own. See §8 for each interface's flow in detail.

## 6. System Specifications

Detailed specifications are organized by system area under this directory: `domain/`, `retrieval/`, `interfaces/`.

Requirements use the identifier format `<TYPE>-<AREA>-<NUMBER>`, e.g. `FR-DM-01` (Functional Requirement, Domain Model). Architectural decisions are documented separately under [`architecture-decisions/`](architecture-decisions/) using the `ADR-NNN` format. See [§10 Requirements Index](#10-requirements-index) for the complete mapping between area prefixes and their specs.

### 6.1 Domain Model
See [Domain Model](domain/domain-model.md)

### 6.2 Structured Data
See [Structured Data](domain/structured-data.md)

### 6.3 Document Corpus
See [Corpus](retrieval/corpus.md)

### 6.4 Retrieval
See [Retrieval](retrieval/retrieval.md)

### 6.5 Ranking
See [Ranking](retrieval/ranking.md)

### 6.6 Context Expansion
See [Context Expansion](retrieval/context-expansion.md)

### 6.7 Backend API
See [API](interfaces/api.md)

### 6.8 Web Viewer
See [Web Viewer](interfaces/web-viewer.md)

### 6.9 Conversational Agent
See [Agent](interfaces/agent.md)

### 6.10 Agnostic (Ad-hoc) Interpretant Query
See [Agnostic Query](interfaces/agnostic-query.md)

### 6.11 Region Augmentation
See [Region Augmentation](interfaces/augmentation.md)

## 7. Architectural Constraints and Invariants

- CON-SYS-01: The codebase enforces, via an automated check, that no domain-specific literal (e.g. tarot-specific terms) appears in the core library or CLI modules — domain content lives only in data files and test fixtures.

These invariants apply across every subsystem in §6 and are not renegotiated per feature:

- Graph retrieval is deterministic and code-driven; no model generates a graph query from user input ([retrieval.md](retrieval/retrieval.md) FR-RT-02).
- Retrieval and ranking are entirely code-driven — no model, including the conversational agent's, participates in deciding what a result *is* ([retrieval.md](retrieval/retrieval.md) FR-RT-03; [ADR-006](architecture-decisions/adr-006-conversational-agent-orchestration-boundary.md)).
- Interpretant matching runs live, per query, against the local vector store — no precomputed interpretant-to-segment match matrix ([retrieval.md](retrieval/retrieval.md) FR-RT-12; [ADR-003](architecture-decisions/adr-003-live-per-interpretant-matching-no-precompute.md)).
- Ranking uses no BM25/rank-fusion; the lexical channel is exact-token containment and specificity-weight document-frequency only ([ranking.md](retrieval/ranking.md); [ADR-002](architecture-decisions/adr-002-dense-plus-exact-token-no-bm25.md), [ADR-004](architecture-decisions/adr-004-absolute-floor-and-lexical-specificity-ranking.md)).

## 8. End-to-End Flows

### 8.1 Structured Data Loading

A curator authors or edits YAML sign files under `data/semiotic_systems/`. `mythrix load-signs` validates schema and referential integrity, then upserts idempotently into the Sign Graph ([structured-data.md](domain/structured-data.md) FR-SD-01/FR-SD-02). Invalid data is rejected before anything is written.

### 8.2 Document Ingestion

A curator supplies a primary-source text plus its colocated source metadata (id, domain, citation label, segmentation scheme). `mythrix load-documents` computes a content hash, segments the source along its declared structure, embeds each segment, and stores it in the vector store ([corpus.md](retrieval/corpus.md)). Re-running on an unchanged file is a no-op; a changed file's segments are replaced.

### 8.3 Web Query

The web viewer submits a region query to the backend API ([api.md](interfaces/api.md) FR-API-01), which runs the same interpretant matching live and rolls it into ranked, specificity-weighted regions ([ranking.md](retrieval/ranking.md)). The viewer renders the ranked list, facets, and a detail panel for the selected hotspot ([web-viewer.md](interfaces/web-viewer.md)).

### 8.4 Conversational Query

A user message in the docked chat panel is sent with the tab's context object. The agent selects and invokes read-only tools ([agent.md](interfaces/agent.md) FR-AG-03), grounding its reply in their results and surfacing a tool trace; the backend detects hotspot/context changes and resets the thread accordingly.

### 8.5 Region Augmentation

An `/augment` command carrying a free-text focus is parsed and held under a generated id, alongside a snapshot of the regions the viewer is displaying; the reply restates the focus, states how many regions a run will read, and names the command that runs it. The matching `/augment-confirm` runs the whole sequence server-side within the turn: for each supplied region in display order, up to a configured bound, a verbatim read of that region's full contiguous ordinal range by structural coordinate and one generation call reading it against the focus — each delivered to the consumer as it lands — then hierarchical map-reduce consolidation of the resulting readings into one answer, grouped and re-grouped in bounded batches until a single result remains (exactly one consolidation call when the run is at or under the batch size). The turn's reply is the consolidation, citing regions by `[R#]` carried forward unchanged from whichever level first assigned them ([augmentation.md](interfaces/augmentation.md), [ADR-016](architecture-decisions/adr-016-hierarchical-map-reduce-augmentation-consolidation.md)).

### 8.6 Hotspot Context Expansion

From a selected hotspot's detail panel, **Add Context** requests adjacent segments from the same source via the backend's segment-range endpoint, filling internal gaps first and then extending each edge up to its chapter boundary or the source's ends ([context-expansion.md](retrieval/context-expansion.md)).

## 9. Reference Implementation

The first reference dataset is tarot (starting with the Rider-Waite tradition). The v1 end-to-end proof is: load a small set of tarot signs/traditions/sources via the structured-data loader, load an excerpt of a public-domain primary source (e.g. Waite's *Pictorial Key to the Tarot*) via the document loader, then query a single sign (e.g. "The Tower") in that tradition via `/api/query` and receive ranked evidence: specificity-weighted regions of converging interpretant matches ([ranking.md](retrieval/ranking.md) FR-RK-01+), each with attribution and verbatim segment text ([retrieval.md](retrieval/retrieval.md) FR-RT-05).

`data/semiotic_systems/tarot/` holds one tradition (`rider-waite`), one source (`waite-pictorial-key`), and all 22 Major Arcana as signs (`data/semiotic_systems/tarot/signs/*.yaml`), each with a Rider-Waite manifestation. Each `denotation` (the card's visual description) is curator-authored, not quoted from Waite. Each `cites` locator points at that card's real section in his 1910 text, fetched from a public-domain digitization. `interpretants` are extracted from each card's `denotation` per [structured-data.md](domain/structured-data.md) FR-SD-05. Each card's intersemiotic interpretant names a Hebrew letter declared in `data/semiotic_systems/hebrew_alef_bet/`, its own sibling reference dataset.

The corpus document is not Waite's own text (see [corpus.md](retrieval/corpus.md) FR-CO-02 — an uploaded document is read through the graph's established symbolism, independent of any source a structured `Manifestation` was extracted from). See [corpus.md § Reference corpus](retrieval/corpus.md#reference-corpus) for the Douay-Rheims Bible and Sefer HaBahir corpus sources used to prove this.

## 10. Requirements Index

| Prefix | Area | Spec | Range |
|---|---|---|---|
| `FR-DM` | Domain Model | [domain/domain-model.md](domain/domain-model.md) | FR-DM-01–FR-DM-05 |
| `FR-SD` | Structured Data | [domain/structured-data.md](domain/structured-data.md) | FR-SD-01–FR-SD-05 |
| `FR-CO` | Corpus | [retrieval/corpus.md](retrieval/corpus.md) | FR-CO-01–FR-CO-18 |
| `FR-RT` | Retrieval | [retrieval/retrieval.md](retrieval/retrieval.md) | FR-RT-01–FR-RT-20, less FR-RT-07–FR-RT-09 (retired) |
| `FR-RK` | Ranking | [retrieval/ranking.md](retrieval/ranking.md) | FR-RK-01–FR-RK-10 |
| `FR-CE` | Context Expansion | [retrieval/context-expansion.md](retrieval/context-expansion.md) | FR-CE-01–FR-CE-15 |
| `FR-API` | Backend API | [interfaces/api.md](interfaces/api.md) | FR-API-01–FR-API-05 |
| `FR-WEB` | Web Viewer | [interfaces/web-viewer.md](interfaces/web-viewer.md) | FR-WEB-01–FR-WEB-31 |
| `FR-AG` | Conversational Agent | [interfaces/agent.md](interfaces/agent.md) | FR-AG-01–FR-AG-47, less FR-AG-19 (retired), plus FR-AG-21a, FR-AG-21b, FR-AG-40a |
| `FR-AQ` | Agnostic (Ad-hoc) Interpretant Query | [interfaces/agnostic-query.md](interfaces/agnostic-query.md) | FR-AQ-01–FR-AQ-22 |
| `FR-CAP` | Agent Capabilities | [interfaces/agent-capabilities.md](interfaces/agent-capabilities.md) | FR-CAP-01–FR-CAP-16 |
| `FR-AU` | Region Augmentation | [interfaces/augmentation.md](interfaces/augmentation.md) | FR-AU-01–FR-AU-41 |
| `CON-SYS` | System-wide constraints | this document, §7 | CON-SYS-01 |

235 active requirements in total.

`FR-RT-07`, `FR-RT-08`, and `FR-RT-09` were retired when region rollup became the sole query result shape ([ADR-013](architecture-decisions/adr-013-region-rollup-sole-query-shape.md)). Unlike the retirements below, they are marked in place in [retrieval.md](retrieval/retrieval.md) rather than removed: the surrounding identifiers stay live and renumbering them would invalidate references in accepted, immutable ADRs. The identifiers are not reused. `FR-AG-19` (the Tarot "cards" feature's structured chat rendering) is marked in place the same way, in [agent.md](interfaces/agent.md).

A prior flat-numbered scheme (`FR1`–`FR102`) was superseded by the identifiers above; six items from that scheme (`FR14`, `FR15`, `FR25`, `FR26`, `FR54`, `FR78`) were retired outright — superseded by the conversational agent's summarize tool replacing an earlier synthesized-summary design — and carry no identifier in the current scheme.

## 11. Architectural Decisions

See [Architectural Decisions](architecture-decisions/).
