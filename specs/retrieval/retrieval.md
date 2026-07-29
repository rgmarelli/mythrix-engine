# Interpretant matching

How a query against one sign and tradition turns into matched segments: the live matching engine every interpretant runs through, whose output is rolled up into ranked regions ([Ranking](ranking.md)) and served by the backend API to the web viewer and the conversational agent.

## Functional requirements

### Query

- FR-RT-01: A query names one sign and one tradition (v1 scope) and returns evidence grounded in (a) deterministic graph retrieval and (b) document retrieval across the full corpus, as one flat, globally ranked list of regions ([ranking.md](ranking.md) FR-RK-01+).
- FR-RT-02: Graph retrieval is deterministic and code-driven — the system never asks an LLM to generate a graph query from user input.
- FR-RT-03: Retrieval and ranking are entirely code-driven; no model participates in deciding what a result *is*. (Applies to the conversational agent layer, [agent.md](../interfaces/agent.md), as well as the `query` path.)
- FR-RT-04: Any generated text the system produces carries a citation marker for every substantive claim, and the system validates in code that each marker refers to material actually present in the retrieved context, rejecting or flagging markers that don't. The `query` path produces no generated text, so this requirement governs the conversational agent layer ([agent.md](../interfaces/agent.md)) only, where the validation code is wired in and exercised.
- FR-RT-05: For every cited document source, the output includes the source's citation label and the verbatim matched segment text itself — not merely a citation marker or locator.
- FR-RT-06: `/api/query` returns a structured payload capturing the full evidentiary chain — region and source identifiers, each constituent segment's ordinal and locator, the verbatim segment text, the embedding model identifier used, and each match's interpretant, kind, score, and the segment ordinal it occurred at — so a result is reproducible and auditable even after the corpus or models change later.

### Retired

- FR-RT-07, FR-RT-08, FR-RT-09: *Retired.* Per-concept result groups, concept-pair result groups, and the pair-membership role of a `"filter"`-directive interpretant. Region rollup is the sole result shape; convergence is a ranking signal rather than a separate group ([ADR-013](../architecture-decisions/adr-013-region-rollup-sole-query-shape.md)). The `"filter"` directive's matching semantics are unchanged and are stated in full by FR-RT-15. These identifiers are not reused.

### Query constraints

- FR-RT-10: The query path invokes no generation model. Answering a query requires the embedding model only.
- FR-RT-11: An interpretant carrying a `query.directive: "skip"` annotation ([corpus.md](corpus.md) FR-CO-03) is excluded from retrieval entirely — no plain query text and no literal-text filter, unlike `"filter"` (FR-RT-15) — while remaining an ordinary fact elsewhere in the Sign Graph (e.g. as a correspondence target's interpretant, still readable via graph queries and any future non-retrieval consumer).

### Region-based matching

This is the matching layer that feeds region rollup ([ranking.md](ranking.md) FR-RK-01+); the backend API exposes its output to the web viewer and the conversational agent. Every interpretant is matched live, per query, against the same graph facts and vector store.

- FR-RT-12: Each interpretant of the queried sign (including interpretants reachable via intersemiotic interpretants, per [corpus.md](corpus.md) FR-CO-03) retrieves its matches independently and at query time — no interpretant's matches are precomputed, and adding or altering an interpretant changes results on the next query with no separate build step.
- FR-RT-13: A concept interpretant matches segments by embedding similarity, using the embedding model only (no generation model), consistent with FR-RT-10.
- FR-RT-14: A concept interpretant matches a segment only when its similarity clears a configurable absolute match floor; below the floor it contributes no match. The floor is an absolute similarity threshold, evaluated per segment against the raw similarity — never a rank cutoff and never a value normalized across the current query's results — so that a corpus not containing the concept yields no match for it rather than a best-of-noise match.
- FR-RT-15: An exact-token interpretant (one carrying a `query.directive: "filter"` annotation, per [corpus.md](corpus.md) FR-CO-03) matches segments by literal containment of its `query.as_token` text rather than by embedding similarity. Containment is evaluated on whole-word boundaries (a token does not match inside a larger word or number) and supports normalization so that a token and its corpus surface forms are treated as equivalent (e.g. a numeric value and its spelled-out forms) — `query.as_token` carries the searched form and is required for this directive, while the interpretant's own `value` is the authored form a match is reported under. Such a match is a *guarantee* that the segment contains that text, not a similarity judgement: it contributes membership but no score, and is not subject to the match floor (FR-RT-14).
- FR-RT-16: An interpretant carrying `query.directive: "skip"` (FR-RT-11) contributes no match of any kind in this path either.
- FR-RT-17: An interpretant carrying a `query.directive: "exact"` annotation ([corpus.md](corpus.md) FR-CO-03) is matched by an exhaustive literal-text scan of the full corpus rather than an embedding search — every chunk containing its token, on whole-word boundaries (FR-RT-15's normalization), is found, with no ranked or capped subset to fall outside of. Its `query.as_token` is optional; when omitted, the scan searches the interpretant's own `value`.
- FR-RT-18: An `"exact"`-directive interpretant contributes no embeddable query at all: its value is never embedded and never reaches an approximate-nearest-neighbour search. This is what distinguishes it from a `"filter"`-directive token (FR-RT-15), which *is* embedded — combined with each concept's own query as an additional literal-text-filtered variant alongside, never instead of, that concept's plain query — and which is applied globally, to every concept reachable from the queried sign rather than only those authored beside it. An `"exact"`-directive interpretant is scoped to its own value alone.
- FR-RT-19: An `"exact"`-directive interpretant's match (FR-RT-17) is membership-only, like a `"filter"`-directive interpretant's (FR-RT-15) — a guarantee of literal containment, carrying no similarity score, since there is no query embedding behind it. A match reached this way is reported distinctly from one reached via a `"filter"`-directive token, so a consumer can tell the two apart.
- FR-RT-20: A region matched by only one interpretant is eligible and rankable when that interpretant is a `"concept"` match or an `"exact"`-directive match ([ranking.md](ranking.md) FR-RK-03) — including an `"exact"`-directive match with no `"concept"` match nearby at all. A region matched exclusively by one or more `"filter"`-directive matches, with no `"concept"` or `"exact"` match within it, is not eligible (FR-RK-03).

## Non-goals

- Precomputing an interpretant-to-segment match matrix, or any hosted/distributed vector-search backend — region retrieval runs live, per query, against the local vector store (FR-RT-12). See [ADR-003](../architecture-decisions/adr-003-live-per-interpretant-matching-no-precompute.md).
