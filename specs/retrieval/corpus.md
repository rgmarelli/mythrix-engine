# Ingestion + segmentation

How primary source documents enter the vector store and are broken into the atomic units that [Retrieval](retrieval.md) and [Ranking](ranking.md) operate over.

## Vocabulary

- **segment**: The atomic retrieval unit — one structurally-bounded piece of a source (e.g. a single scripture verse or numbered section), carrying exact structural coordinates and a stable ordinal position within its source.
- **structural coordinates**: The source-relative reference locating a segment (e.g. source id, chapter/section, verse/ordinal), sufficient to render a human-readable locator and to determine whether two segments are contiguous within the same source.

## Functional requirements

### Document ingestion

- FR-CO-01: The document loader ingests primary source texts, chunks them, embeds them via the local embedding model, and stores them with metadata sufficient to filter by domain and to reconstruct a human-readable citation (the source's citation label, locator). A document's `Source` carries no `Tradition` — it is identified by an explicitly authored id and a domain, both declared in the source's own structured-data file, colocated with the raw text it describes.
- FR-CO-02: Retrieval at query time always searches the full ingested document corpus — an uploaded document (e.g. a scriptural or literary text) is an independent corpus to be read *through* the graph's established symbolism, never scoped to a tradition, since a corpus document has no interpretive tradition of its own. This is distinct from comparing multiple *interpretive* traditions of the same sign against each other (e.g. Crowley's vs. Waite's reading of a card), which remains out of scope for v1 (see [domain-model.md](../domain/domain-model.md) Non-goals). An explicit scoping mechanism to keep a second interpretive tradition's commentary from blending into retrieval does not exist yet (see `plan.md` Risks).
- FR-CO-03: The text used to drive similarity search is derived from retrieved graph facts — an interpretant's `value`, never a sign's or manifestation's `properties`, and never a sign's canonical name or a manifestation's denotation, and never raw, unvalidated user input. This includes the whole graph reachable from the queried sign via `intersemiotic_interpretants` ([domain-model.md](../domain/domain-model.md) FR-DM-03, [structured-data.md](../domain/structured-data.md) FR-SD-04) — each target sign's own interpretants are folded into the query too, but never the target's properties. An interpretant carrying a `query.directive: "filter"` annotation is excluded from the plain query text and is instead applied as an additional literal-text filter using its `query.as_token` value, alongside — never instead of — every other interpretant's plain query. An interpretant carrying a `query.directive: "skip"` annotation ([retrieval.md](retrieval.md) FR-RT-11) is excluded from retrieval entirely.
- FR-CO-04: The document loader computes a content hash of each ingested source file and records it on the corresponding `Source`. Re-running the loader with an unchanged file is a no-op (idempotent, no duplicate chunks); re-running with a changed file replaces that source's previously ingested chunks rather than accumulating stale ones alongside the new content.

### Segmentation

- FR-CO-05: The document loader segments a source along its own declared structure into atomic segments (one segment per smallest structural unit the source declares, e.g. a verse or a numbered section), rather than into fixed word-count windows, when the source declares a segmentation scheme; a source with no declared scheme falls back to fixed-size chunking. A segment never spans a structural boundary of its source, and no segment overlaps another.
- FR-CO-06: Each segment records exact structural coordinates and a stable ordinal position within its source, sufficient to (a) render a human-readable locator and (b) determine contiguity — whether one segment immediately follows another in the same source. Any structural-label prefix (e.g. a leading verse or section number) is excluded from the segment's matchable text so that it neither influences embedding nor produces spurious token containment.
- FR-CO-07: Segmentation is content-hash idempotent per source (FR-CO-04): re-ingesting an unchanged source is a no-op; re-ingesting a changed source replaces that source's segments.

## Reference corpus

`data/corpus/scripture/en_drb/` provides the complete Douay-Rheims Bible (Old and New Testament, public domain) as an independent corpus source — its `.yaml` (id, domain, citation label, bibliographic metadata) colocated with the raw `.txt` it describes, carrying no `Tradition` (FR-CO-01) — meant to be read *through* the tarot signs' established meanings rather than treated as their source. It declares a `scripture_verse` segmentation scheme (FR-CO-05), one segment per verse. `data/corpus/kabbalah/en_bahir/` provides the Sefer HaBahir as a second corpus source, declaring a `numbered_section` scheme, one segment per numbered section — proving segmentation is source-declared and corpus-agnostic, not scripture-specific.
