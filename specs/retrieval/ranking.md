# Region ranking

How interpretant matches ([retrieval.md](retrieval.md)) are aggregated into regions and ranked — the "hotspot" data the web viewer and backend API present.

## Vocabulary

- **match floor**: An absolute lower bound on a concept interpretant's similarity, below which the interpretant is treated as not matching that segment.
- **region**: A bounded span of contiguous segments within a single source over which interpretant matches are aggregated and ranked (a single segment, a structural section, or a sliding window of N consecutive segments).
- **specificity weight**: A per-interpretant weight derived from how many units of the corpus contain a surface form of that interpretant — a rarer surface form yields a higher weight.
- **hotspot**: The web viewer's display term for a ranked region.

## Functional requirements

- FR-RK-01: Interpretant matches are aggregated to the region: for each region and each interpretant, the region retains that interpretant's single best surviving match within it (best floor-clearing similarity for a concept interpretant; presence for an exact-token interpretant).
- FR-RK-02: A region's convergence is defined over contiguous segments of a single source. The region granularity is a configurable parameter of the query — a single segment, a structural section, or a window of N consecutive units — not a fixed constant.
- FR-RK-03: A region is eligible to be ranked when at least a configurable minimum number of distinct interpretants match within it. The minimum defaults to one: a region matched by a single interpretant (an isolated match) is eligible and rankable. Convergence is therefore a ranking signal, not an eligibility gate. A region's reported convergence count is the number of distinct interpretants matching within it.
- FR-RK-04: Each interpretant carries a specificity weight derived from the document frequency of its surface form across the corpus — the number of corpus units containing that surface form — such that a rarer surface form yields a strictly higher weight, and a ubiquitous one a lower weight.
- FR-RK-05: A region's convergence score is the sum, over the interpretants matching within it, of each interpretant's specificity weight multiplied by that interpretant's best match strength within the region. A concept interpretant's match strength is its raw floor-clearing similarity; an exact-token interpretant's is a fixed presence value. Regions are ranked by this score, descending. Because the score sums over matching interpretants, a region matched by more distinct interpretants tends to rank above one matched by fewer of comparable strength — convergence raises rank as an emergent property of the sum, not through a separate gate.
- FR-RK-06: The specificity weight is computed from literal surface-form frequency, not from embedding-similarity score distributions. Match strength entering the score is raw floor-clearing similarity, not a value min-max normalized within the query's results, so absolute match quality is preserved and comparable across queries and corpora.
- FR-RK-07: A region query returns a ranked list of regions. Each region reports its structural locator, its convergence count and convergence score, the constituent interpretants that matched it (one or more), and, per interpretant, that interpretant's best match within the region (its similarity score, or a containment indication for an exact-token interpretant).
- FR-RK-08: For each region, the output includes the verbatim text of the constituent segment(s) that carried the matches, addressable by their structural coordinates — not merely a locator or a marker (consistent with [retrieval.md](retrieval.md) FR-RT-05). A segment's verbatim text appears once per region regardless of how many interpretants matched it.
- FR-RK-09: Each interpretant's match anchors to the specific constituent segment that carried it (by that segment's structural coordinates), so a result reveals not only that an interpretant matched the region but exactly where within it — enabling a consumer to navigate directly to the matching segment rather than re-scanning the region.
- FR-RK-10: Results preserve per-interpretant attribution as first-class data so the web viewer ([web-viewer.md](../interfaces/web-viewer.md) FR-WEB-02) can display which interpretants matched, count them, filter by them, and navigate to each one's matching segment — without recomputation.

## Non-goals

- Lexical relevance ranking (BM25/SPLADE) or rank-fusion across interpretants (e.g. RRF) as a region-ranking mechanism (FR-RK-01–FR-RK-06). The lexical channel is used only for exact-token containment matching ([retrieval.md](retrieval.md) FR-RT-15) and for the specificity-weight document-frequency counts (FR-RK-04), never to rank regions. See [ADR-002](../architecture-decisions/adr-002-dense-plus-exact-token-no-bm25.md) and [ADR-004](../architecture-decisions/adr-004-absolute-floor-and-lexical-specificity-ranking.md).
- Automatic detection of semantic/topic region boundaries. A region is a contiguous span defined by structural coordinates and a configurable window size (FR-RK-02), not by inferred topic shifts. See [ADR-001](../architecture-decisions/adr-001-structural-segmentation-and-region-rollup.md).
