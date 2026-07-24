# Concept/pair retrieval

How a query against one sign and tradition turns into matched segments — two paths sharing the same live matching engine: per-concept/concept-pair retrieval (CLI, this document) and region rollup ([Ranking](ranking.md)), which the web viewer and backend API expose.

## Functional requirements

### Query / synthesis

- FR-RT-01: A query names one sign and one tradition (v1 scope) and returns evidence grounded in (a) deterministic graph retrieval and (b) document retrieval across the full corpus, organized per concept (FR-RT-07) and per concept pair (FR-RT-08).
- FR-RT-02: Graph retrieval is deterministic and code-driven — the system never asks an LLM to generate a graph query from user input.
- FR-RT-03: Retrieval and ranking are entirely code-driven; no model participates in deciding what a result *is*. (Applies to the conversational agent layer, [agent.md](../interfaces/agent.md), as well as the `query` path.)
- FR-RT-04: Any generated text the system produces carries a citation marker for every substantive claim, and the system validates in code that each marker refers to material actually present in the retrieved context, rejecting or flagging markers that don't. The `query` path produces no generated text, so this requirement governs the conversational agent layer ([agent.md](../interfaces/agent.md)) only, where the validation code is wired in and exercised.
- FR-RT-05: For every cited document source, the output includes the source's citation label and the verbatim retrieved passage/paragraph text itself — not merely a citation marker or locator. This applies to both human-readable and JSON output.
- FR-RT-06: The CLI supports a structured (JSON) output mode capturing the full evidentiary chain — graph fact identifiers, retrieved chunk identifiers/offsets, retrieved passage text, the embedding model identifier used, and per-concept-pair membership and match scores (FR-RT-08) — so a result is reproducible and auditable even after the corpus or models change later. Every `Source`/`Tradition` referenced anywhere in the result is listed once under top-level `sources`/`traditions` tables keyed by id, with passages/manifestations referencing them by `source_id`/`tradition_id` rather than embedding the full object per citation. Marker numbering is the 1-based position within each list.

### Concept-scoped retrieval

- FR-RT-07: Retrieval is organized per concept — each individually-queried graph fact (an interpretant's value, or an intersemiotic interpretant's target interpretant, per [corpus.md](corpus.md) FR-CO-03's query decomposition) retrieves its own candidate passages independently, rather than every query's hits being merged into one shared pool before any cutoff is applied. Each concept gets its own retrieval budget.

### Concept-pair convergence

- FR-RT-08: Where two concepts both retrieve the same passage, the system emits an additional result group keyed by that concept pair, ranked independently and displayed alongside — never instead of — the per-concept groups of FR-RT-07. Pair membership is detected against a retrieval pool deeper than the one displayed. A passage matched by three or more concepts appears in each of its constituent pairs. Each pair result carries a combined match score derived from the underlying similarity scores rather than from ordinal rank, together with the per-concept component scores it was derived from.
- FR-RT-09: An interpretant carrying a `query.directive: "filter"` annotation ([corpus.md](corpus.md) FR-CO-03) appears as a first-class member of a pair alongside semantic concepts, so a result can read as "child + 100". Such an interpretant reaches a passage through a literal text filter rather than through embedding similarity: its membership is a guarantee that the passage contains its `query.as_token` text, not a similarity judgement. It contributes membership but no score; a pair combining one semantic concept with one exact-filter interpretant is scored by the semantic concept alone.
- FR-RT-10: The query path invokes no generation model. Answering a query requires the embedding model only.
- FR-RT-11: An interpretant carrying a `query.directive: "skip"` annotation ([corpus.md](corpus.md) FR-CO-03) is excluded from retrieval entirely — no plain query text and no literal-text filter, unlike `"filter"` (FR-RT-09) — while remaining an ordinary fact elsewhere in the Sign Graph (e.g. as a correspondence target's interpretant, still readable via graph queries and any future non-retrieval consumer).

### Region-based matching

This is the matching layer that feeds region rollup ([ranking.md](ranking.md) FR-RK-01+); the web viewer and backend API expose its output, while `mythrix query` exposes the per-concept/concept-pair results above. Both paths match every interpretant live, per query, against the same graph facts and vector store.

- FR-RT-12: Each interpretant of the queried sign (including interpretants reachable via intersemiotic interpretants, per [corpus.md](corpus.md) FR-CO-03) retrieves its matches independently and at query time — no interpretant's matches are precomputed, and adding or altering an interpretant changes results on the next query with no separate build step.
- FR-RT-13: A concept interpretant matches segments by embedding similarity, using the embedding model only (no generation model), consistent with FR-RT-10.
- FR-RT-14: A concept interpretant matches a segment only when its similarity clears a configurable absolute match floor; below the floor it contributes no match. The floor is an absolute similarity threshold, evaluated per segment against the raw similarity — never a rank cutoff and never a value normalized across the current query's results — so that a corpus not containing the concept yields no match for it rather than a best-of-noise match.
- FR-RT-15: An exact-token interpretant (one carrying a `query.directive: "filter"` annotation, per [corpus.md](corpus.md) FR-CO-03 / FR-RT-09) matches segments by literal containment of its token rather than by similarity. Containment is evaluated on whole-word boundaries (a token does not match inside a larger word or number) and supports normalization so that a token and its corpus surface forms are treated as equivalent (e.g. a numeric value and its spelled-out forms). A containment match contributes membership, not a similarity score, and is not subject to the match floor.
- FR-RT-16: An interpretant carrying `query.directive: "skip"` (FR-RT-11) contributes no match of any kind in this path either.

## Non-goals

- Precomputing an interpretant-to-segment match matrix, or any hosted/distributed vector-search backend — region retrieval runs live, per query, against the local vector store (FR-RT-12). See [ADR-003](../architecture-decisions/adr-003-live-per-interpretant-matching-no-precompute.md).
