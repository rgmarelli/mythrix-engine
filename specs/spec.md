# Symbol Interpretation Core — Spec

## Problem

Existing symbolic-interpretation tools fall into two unsatisfying categories: opaque divinatory black boxes that offer no reasoning trail, or unstructured LLM wrappers that generate plausible-sounding but invented interpretations. Researchers and practitioners working in comparative symbolism, digital humanities, and related fields need a tool where every conclusion is traceable back to (a) the specific symbols identified, (b) the primary sources retrieved, and (c) the reasoning chain connecting them — with interpretive traditions kept distinct rather than blended into one composite "meaning."

## Vocabulary

- **`semiotic_system`**: The overarching domain or system of signs being classified (e.g., `tarot`, `hebrew_alef_bet`).
- **`sign`**: The single, primary symbol or entity being modeled in a file (e.g., The Sun, Qoph).
- **`manifestations`**: The specific historical, cultural, or textual traditions where a sign is contextualized and described (e.g., `rider-waite`, `sepher-yetzirah-gra`).
- **`properties`**: Static, structural attributes of a sign (e.g., card number, letter type). They provide informational context but are never used for dynamic search queries.
- **`interpretants`**: The conceptual tokens, values, or meanings evoked by a sign within its own domain — the primary source of retrieval query text.
- **`intersemiotic_interpretants`**: Graph-edge pointers that bridge distinct domains, mapping how a sign translates directly into a specific target sign of an external system.
- **segment**: The atomic retrieval unit — one structurally-bounded piece of a source (e.g. a single scripture verse or numbered section), carrying exact structural coordinates and a stable ordinal position within its source.
- **structural coordinates**: The source-relative reference locating a segment (e.g. source id, chapter/section, verse/ordinal), sufficient to render a human-readable locator and to determine whether two segments are contiguous within the same source.
- **match floor**: An absolute lower bound on a concept interpretant's similarity, below which the interpretant is treated as not matching that segment.
- **region**: A bounded span of contiguous segments within a single source over which interpretant matches are aggregated and ranked (a single segment, a structural section, or a sliding window of N consecutive segments).
- **specificity weight**: A per-interpretant weight derived from how many units of the corpus contain a surface form of that interpretant — a rarer surface form yields a higher weight.
- **hotspot**: The web viewer's display term for a ranked region.
- **agent**: A tool-calling loop, driven by a local chat model, that turns a natural-language request into calls against Mythrix's existing operations and reports the results conversationally.
- **tool**: A single, typed, read-only operation the agent may invoke, wrapping an existing Mythrix service function (e.g. run a query, fetch a segment range).
- **turn**: One user message plus the agent's full response to it, including any tool calls made while producing that response.
- **session**: An ordered series of turns sharing conversation history.
- **tool trace**: The ordered record of which tools the agent called during a turn, surfaced to the user so the evidence path is visible.
- **matched segment**: A hotspot segment that carried at least one interpretant match — the only segments the detail panel shows before any context is added.
- **context segment**: A verbatim segment from the same source, loaded into the detail panel on demand, that carried no interpretant match.
- **internal gap**: A non-matching segment whose ordinal lies strictly between a hotspot's lowest and highest matched ordinal, absent from the hotspot as returned.
- **leading edge / trailing edge**: The lowest-ordinal and highest-ordinal segment currently loaded in a hotspot's detail panel (matched or context).
- **chapter boundary**: The first/last segment of the structural section (`Segment.section`, e.g. a scripture chapter or a numbered section) that an edge segment belongs to. A source that declares no such structure has no chapter boundary; its only bounds are the source's first and last segment.
- **thread**: The portion of an agent chat session's history scoped to one active hotspot. Selecting a different hotspot starts a new thread; a thread never merges with or extends a prior one.
- **tab**: An independent unit of web-viewer workspace state — one semiotic system/symbol/tradition/min-score selection, its facet selections, its query result (if any), its selected hotspot, and its own agent chat session and thread. Tabs never share or merge state with one another.

## Goals

- A **domain-agnostic Sign Graph** data model representing signs, interpretive traditions, tradition-scoped manifestations, properties, interpretants, and intersemiotic interpretants (including cross-tradition, cross-domain, and alternative/competing claims), and sources — with no distinct meaning ever collapsing into another's, whether the distinction comes from tradition, from a competing attribution system, or from a nested context within a domain (e.g. a sign's manifestation within a specific sub-concept of its domain).
- A **RAG pipeline** grounded in curated primary-source documents, searched as one independent corpus rather than scoped by interpretive tradition.
- A **local-only pipeline** (no hosted API dependency) that returns ranked, cited evidence for a query — retrieved graph facts and source passages — rather than a generated narrative. Citation-validation machinery is retained for the conversational agent layer (FR58–FR70, FR94–FR102), which is where any generated text belongs.
- **Three tools sharing one core library**:
  - A CLI for querying/interpreting symbols.
  - A structured-data loader that populates the Sign Graph from human-authored data.
  - A document loader that ingests primary source texts into the RAG vector store.
- **Tarot as the first reference dataset**, used to prove a single-sign, single-tradition query end-to-end through the full pipeline (CLI → graph retrieval → document retrieval → ranked concept and concept-pair evidence, per FR27–FR29).
- **Structural, source-declared segmentation** of corpus documents into atomic segments (verses, numbered sections), with contiguous segments rolled up into specificity-weighted, ranked regions — a second retrieval path alongside per-concept/concept-pair retrieval, sharing the same live per-interpretant matching engine (FR31–FR48).
- **A web viewer and an independent backend HTTP API** presenting the same evidentiary content as the CLI — sign/tradition selection, a single ranked list of regions, AND-combined facets, and a region detail view with full verbatim text and citation — reusing the core retrieval pipeline and stores with no duplicated logic (FR49–FR57).
- **An in-app conversational agent**, served by the backend API and surfaced as a docked chat panel in the web viewer, that operates the existing retrieval pipeline through a fixed set of read-only tools — discovery, symbol facts, region query, segment-range fetch, and passage summarization — grounding every claim in a tool result and its citation, on a local generation model only, with a structured working-memory object and hotspot-scoped conversation threads (FR58–FR70, FR94–FR102).
- **An in-panel "Add Context" control** in the web viewer that progressively loads verbatim context around a hotspot's matched segments, bounded by the source's own chapter/section structure (FR71–FR83).
- **A tabbed workspace** in the web viewer — multiple independent queries held open at once, each with its own facets/result/selected hotspot and its own grounded agent conversation — with the whole viewer, including the agent panel, sharing one visual design system (FR84–FR93).

## Non-goals (v1)

- Multi-symbol or spread-style queries (e.g. interpreting several symbols together in one request).
- Cross-tradition comparison synthesis as a query capability — e.g. surfacing two *interpretive* traditions' competing readings of the same symbol (Crowley's vs. Waite's) side by side and adjudicating which one a document corpus better supports. The data model must support intersemiotic interpretants between traditions, but no query surface for comparing traditions ships in v1. (This is distinct from FR7 — retrieving from an independent, non-interpretive document corpus like a scriptural text through one tradition's established symbolism is in scope; comparing two competing interpretive traditions against each other is not.)
- Conversational or free-text natural-language request parsing — v1 uses structured CLI arguments only. A conversational agent layer (an agent loop driving a fixed, read-only tool set) exists as an in-app chat panel served by the backend API (FR58–FR70, FR94–FR102), outside v1's scope and must not be precluded by v1's design. The prompt-rendering, marker-enumeration, citation-validation, and Ollama-client modules exist for that layer; the v1 `query` path does not invoke them.
- Hardening against adversarial input / prompt injection beyond baseline mitigations (data-not-instructions framing, citation-id validation). Full adversarial hardening is deferred; v1 assumes curator-supplied, not arbitrary, source documents.
- Verifying that LLM paraphrases are faithful to their cited source, beyond confirming the citation marker refers to real, in-context material. Faithfulness/entailment checking is future work.
- Concurrent multi-process write access to the graph store or vector store.
- Sentiment analysis — not designed or scoped here; deferred to the conversational agent layer. Tracked as an open idea in `docs/TODO.md`, not a v1 deliverable.
- Lexical relevance ranking (BM25/SPLADE) or rank-fusion across interpretants (e.g. RRF) as a region-ranking mechanism (FR39–FR44). The lexical channel is used only for exact-token containment matching (FR37) and for the specificity-weight document-frequency counts (FR42), never to rank regions.
- Precomputing an interpretant-to-segment match matrix, or any hosted/distributed vector-search backend — region retrieval runs live, per query, against the local vector store (FR34).
- Automatic detection of semantic/topic region boundaries. A region is a contiguous span defined by structural coordinates and a configurable window size (FR40), not by inferred topic shifts.
- Authentication, multi-user access, or any access control on the web viewer or backend API.
- Write operations from the web viewer beyond the structured-data reload endpoint (FR55) — loading structured data or documents from scratch stays CLI-only (FR57).
- A UI for comparing multiple interpretive traditions of the same sign against each other (consistent with the cross-tradition-comparison Non-goal above).
- Concurrent execution of the backend API process and a `load-symbols`/`load-documents` CLI invocation against the same graph/vector store paths (FR56) — each opens its own connection to the graph database's single-writer lock; the reload endpoint (FR55) is exempt, since it reuses the API process's already-open connection rather than opening a second one.
- Any mutating/administrative tool in the conversational agent's tool set (ingesting symbols/documents, reloading stores), a cloud/hosted generation model, or persisting agent sessions across process restarts; the agent is an orchestration and presentation layer that introduces no new retrieval, ranking, or convergence behavior and does not parse free text into retrieval query text (FR58–FR70, FR94–FR102).
- The agent returning an instruction that mutates application state on its own — changing a facet or min-score, navigating to a different hotspot, or opening/closing a tab from chat. The agent only ever answers conversationally and updates its own context object (FR97); this is deferred, not precluded by the context-object design.
- Merging multiple hotspots of the same source into one continuous reading view, crossing a chapter/section boundary during context expansion, persisting a hotspot's expansion state across queries or browser reloads, re-running a similarity search to fetch context, or a one-click affordance to load an entire chapter/source at once; context segments never affect retrieval, ranking, convergence scoring, or facet counts (FR71–FR83).

## Functional requirements

### Sign Graph (structured data)

- FR1: The system represents `Sign`, `Tradition`, `Manifestation` (a sign as understood within one tradition), `Property`, `Interpretant`, and `Source` as distinct entities, with no domain-specific fields baked into the core schema.
- FR2: A sign may have multiple `Manifestation`s, one per tradition, each with its own display name/title (a sign's name is not assumed to be tradition-invariant — e.g. the same tarot card may be titled differently across traditions), denotation, properties, interpretants, and citations, all scoped to that manifestation only.
- FR3: Intersemiotic interpretants between signs (including across traditions, across domains — e.g. a tarot sign related to a Kabbalah sign — and across nested sub-contexts within a domain, e.g. a concept that manifests distinctly within each of several parallel contexts such as a sephirah within a given "world") are first-class, typed (a free-text relationship, not a fixed enum), and attributable: each intersemiotic interpretant records which tradition/attribution-system asserts it (`according_to`) and may cite a source, so multiple alternative or competing claims can coexist for the same sign without conflicting or silently overwriting one another. No domain-specific structural concepts (such as a fixed notion of "world" or "level") are introduced into the core schema — nested contexts are represented as ordinary data using the same sign/manifestation/intersemiotic-interpretant primitives.
- FR4: The structured-data loader accepts human-authored, version-controllable source files, validates their schema and referential integrity (e.g. a citation must reference an already-loaded source; an intersemiotic interpretant must reference existing sign/tradition pairs) before writing anything, and upserts idempotently — re-running the loader on edited data does not create duplicates.
- FR5: Invalid or referentially inconsistent structured data is rejected with an actionable error, not silently partially loaded.

### Document corpus (RAG)

- FR6: The document loader ingests primary source texts, chunks them, embeds them via the local embedding model, and stores them with metadata sufficient to filter by domain and to reconstruct a human-readable citation (the source's citation label, locator). A document's `Source` carries no `Tradition` — it is identified by an explicitly authored id and a domain, both declared in the source's own structured-data file, colocated with the raw text it describes.
- FR7: Retrieval at query time always searches the full ingested document corpus — an uploaded document (e.g. a scriptural or literary text) is an independent corpus to be read *through* the graph's established symbolism, never scoped to a tradition, since a corpus document has no interpretive tradition of its own. This is distinct from comparing multiple *interpretive* traditions of the same sign against each other (e.g. Crowley's vs. Waite's reading of a card), which remains out of scope for v1 (see Non-goals). An explicit scoping mechanism to keep a second interpretive tradition's commentary from blending into retrieval does not exist yet (see `plan.md` Risks).
- FR8: The text used to drive similarity search is derived from retrieved graph facts — an interpretant's `value`, never a sign's or manifestation's `properties`, and never a sign's canonical name or a manifestation's denotation, and never raw, unvalidated user input. This includes the whole graph reachable from the queried sign via `intersemiotic_interpretants` (FR3, FR19) — each target sign's own interpretants are folded into the query too, but never the target's properties. An interpretant carrying a `query.directive: "filter"` annotation is excluded from the plain query text and is instead applied as an additional literal-text filter using its `query.as_token` value, alongside — never instead of — every other interpretant's plain query. An interpretant carrying a `query.directive: "skip"` annotation (FR30) is excluded from retrieval entirely.
- FR23: The document loader computes a content hash of each ingested source file and records it on the corresponding `Source`. Re-running the loader with an unchanged file is a no-op (idempotent, no duplicate chunks); re-running with a changed file replaces that source's previously ingested chunks rather than accumulating stale ones alongside the new content.

### Query / synthesis

- FR9: A query names one sign and one tradition (v1 scope) and returns evidence grounded in (a) deterministic graph retrieval and (b) document retrieval across the full corpus, organized per concept (FR24) and per concept pair (FR27).
- FR10: Graph retrieval is deterministic and code-driven — the system never asks an LLM to generate a graph query from user input.
- FR11: Retrieval and ranking are entirely code-driven; no model participates in deciding what a result *is*. (Applies to the planned agent layer as well as the `query` path.)
- FR12: Any generated text the system produces carries a citation marker for every substantive claim, and the system validates in code that each marker refers to material actually present in the retrieved context, rejecting or flagging markers that don't. The `query` path produces no generated text, so this requirement governs the conversational agent layer (FR58–FR70, FR94–FR102) only, where the validation code is wired in and exercised.
- FR13: For every cited document source, the output includes the source's citation label and the verbatim retrieved passage/paragraph text itself — not merely a citation marker or locator. This applies to both human-readable and JSON output.
- FR16: The CLI supports a structured (JSON) output mode capturing the full evidentiary chain — graph fact identifiers, retrieved chunk identifiers/offsets, retrieved passage text, the embedding model identifier used, and per-concept-pair membership and match scores (FR27) — so a result is reproducible and auditable even after the corpus or models change later. Every `Source`/`Tradition` referenced anywhere in the result is listed once under top-level `sources`/`traditions` tables keyed by id, with passages/manifestations referencing them by `source_id`/`tradition_id` rather than embedding the full object per citation. Marker numbering is the 1-based position within each list.

### Concept-scoped retrieval

- FR24: Retrieval is organized per concept — each individually-queried graph fact (an interpretant's value, or an intersemiotic interpretant's target interpretant, per FR8's query decomposition) retrieves its own candidate passages independently, rather than every query's hits being merged into one shared pool before any cutoff is applied. Each concept gets its own retrieval budget.

### Concept-pair convergence

- FR27: Where two concepts both retrieve the same passage, the system emits an additional result group keyed by that concept pair, ranked independently and displayed alongside — never instead of — the per-concept groups of FR24. Pair membership is detected against a retrieval pool deeper than the one displayed. A passage matched by three or more concepts appears in each of its constituent pairs. Each pair result carries a combined match score derived from the underlying similarity scores rather than from ordinal rank, together with the per-concept component scores it was derived from.
- FR28: An interpretant carrying a `query.directive: "filter"` annotation (FR8) appears as a first-class member of a pair alongside semantic concepts, so a result can read as "child + 100". Such an interpretant reaches a passage through a literal text filter rather than through embedding similarity: its membership is a guarantee that the passage contains its `query.as_token` text, not a similarity judgement. It contributes membership but no score; a pair combining one semantic concept with one exact-filter interpretant is scored by the semantic concept alone.
- FR29: The query path invokes no generation model. Answering a query requires the embedding model only.
- FR30: An interpretant carrying a `query.directive: "skip"` annotation (FR8) is excluded from retrieval entirely — no plain query text and no literal-text filter, unlike `"filter"` (FR28) — while remaining an ordinary fact elsewhere in the Sign Graph (e.g. as a correspondence target's interpretant, still readable via graph queries and any future non-retrieval consumer).

### Corpus segmentation

- FR31: The document loader segments a source along its own declared structure into atomic segments (one segment per smallest structural unit the source declares, e.g. a verse or a numbered section), rather than into fixed word-count windows, when the source declares a segmentation scheme; a source with no declared scheme falls back to fixed-size chunking. A segment never spans a structural boundary of its source, and no segment overlaps another.
- FR32: Each segment records exact structural coordinates and a stable ordinal position within its source, sufficient to (a) render a human-readable locator and (b) determine contiguity — whether one segment immediately follows another in the same source. Any structural-label prefix (e.g. a leading verse or section number) is excluded from the segment's matchable text so that it neither influences embedding nor produces spurious token containment.
- FR33: Segmentation is content-hash idempotent per source (FR23): re-ingesting an unchanged source is a no-op; re-ingesting a changed source replaces that source's segments.

### Region-based retrieval

This is a second retrieval path alongside concept/concept-pair retrieval (FR24, FR27–FR28): the CLI's `mythrix query` exposes per-concept and concept-pair results, while the web viewer and backend API (FR49) expose the ranked-region results below. Both paths match every interpretant live, per query, against the same graph facts and vector store.

- FR34: Each interpretant of the queried sign (including interpretants reachable via intersemiotic interpretants, per FR8) retrieves its matches independently and at query time — no interpretant's matches are precomputed, and adding or altering an interpretant changes results on the next query with no separate build step.
- FR35: A concept interpretant matches segments by embedding similarity, using the embedding model only (no generation model), consistent with FR29.
- FR36: A concept interpretant matches a segment only when its similarity clears a configurable absolute match floor; below the floor it contributes no match. The floor is an absolute similarity threshold, evaluated per segment against the raw similarity — never a rank cutoff and never a value normalized across the current query's results — so that a corpus not containing the concept yields no match for it rather than a best-of-noise match.
- FR37: An exact-token interpretant (one carrying a `query.directive: "filter"` annotation, per FR8/FR28) matches segments by literal containment of its token rather than by similarity. Containment is evaluated on whole-word boundaries (a token does not match inside a larger word or number) and supports normalization so that a token and its corpus surface forms are treated as equivalent (e.g. a numeric value and its spelled-out forms). A containment match contributes membership, not a similarity score, and is not subject to the match floor.
- FR38: An interpretant carrying `query.directive: "skip"` (FR30) contributes no match of any kind in this path either.

### Region rollup and ranking

- FR39: Interpretant matches are aggregated to the region: for each region and each interpretant, the region retains that interpretant's single best surviving match within it (best floor-clearing similarity for a concept interpretant; presence for an exact-token interpretant).
- FR40: A region's convergence is defined over contiguous segments of a single source. The region granularity is a configurable parameter of the query — a single segment, a structural section, or a window of N consecutive units — not a fixed constant.
- FR41: A region is eligible to be ranked when at least a configurable minimum number of distinct interpretants match within it. The minimum defaults to one: a region matched by a single interpretant (an isolated match) is eligible and rankable. Convergence is therefore a ranking signal, not an eligibility gate. A region's reported convergence count is the number of distinct interpretants matching within it.
- FR42: Each interpretant carries a specificity weight derived from the document frequency of its surface form across the corpus — the number of corpus units containing that surface form — such that a rarer surface form yields a strictly higher weight, and a ubiquitous one a lower weight.
- FR43: A region's convergence score is the sum, over the interpretants matching within it, of each interpretant's specificity weight multiplied by that interpretant's best match strength within the region. A concept interpretant's match strength is its raw floor-clearing similarity; an exact-token interpretant's is a fixed presence value. Regions are ranked by this score, descending. Because the score sums over matching interpretants, a region matched by more distinct interpretants tends to rank above one matched by fewer of comparable strength — convergence raises rank as an emergent property of the sum, not through a separate gate.
- FR44: The specificity weight is computed from literal surface-form frequency, not from embedding-similarity score distributions. Match strength entering the score is raw floor-clearing similarity, not a value min-max normalized within the query's results, so absolute match quality is preserved and comparable across queries and corpora.
- FR45: A region query returns a ranked list of regions. Each region reports its structural locator, its convergence count and convergence score, the constituent interpretants that matched it (one or more), and, per interpretant, that interpretant's best match within the region (its similarity score, or a containment indication for an exact-token interpretant).
- FR46: For each region, the output includes the verbatim text of the constituent segment(s) that carried the matches, addressable by their structural coordinates — not merely a locator or a marker (consistent with FR13). A segment's verbatim text appears once per region regardless of how many interpretants matched it.
- FR47: Each interpretant's match anchors to the specific constituent segment that carried it (by that segment's structural coordinates), so a result reveals not only that an interpretant matched the region but exactly where within it — enabling a consumer to navigate directly to the matching segment rather than re-scanning the region.
- FR48: Results preserve per-interpretant attribution as first-class data so the web viewer (FR49) can display which interpretants matched, count them, filter by them, and navigate to each one's matching segment — without recomputation.

### Web viewer and backend API

- FR49: A backend HTTP API, a process independent of the CLI, serves sign/tradition listings and region query results as JSON, executed through the existing retrieval pipeline and graph/vector stores with no duplicated graph-query or retrieval logic. A web viewer presents this content without requiring the CLI or reading raw JSON.
- FR50: Within each open tab (FR84), the web viewer presents a form to select one semiotic system, one sign, and one tradition, the sign selector scoped by the chosen semiotic system, restricted to sign/tradition combinations that have a manifestation.
- FR51: Within a tab, a query result is a single ranked list of regions (FR45), together with facet data: one entry per corpus source with a count of matching regions, and one entry per interpretant with a count of regions it matched. Two independent, AND-combined, single-select facets (Sources, Interpretants) filter the displayed region list; selecting a value in one facet with the other left at "All" filters across every value of the other. Each facet's counts (including "All") are scoped to the region set satisfying the *other* facet's current selection, recomputed whenever either selection changes; a facet's own selection never scopes its own counts.
- FR52: A region list shows each region's title, its convergence count, and which interpretants matched it; the active/selected region is visually distinguished. A detail panel shows the selected region's full verbatim segment text and complete citation, with no client-side truncation, one chip per matched interpretant with its individual match (the interpretant(s) satisfying the active facet filter visually distinguished from the rest, none hidden), navigation to the previous/next region within the current filtered, ranked list, and an action to copy the region's citation/reference string.
- FR53: The query form offers an optional minimum-score input, applied to the next query submission only; left blank, no override is sent and the server's own default governs.
- FR55: An API endpoint re-reads structured sign/tradition/source data from disk and upserts it into the graph store already open for the running API process, without requiring the process to be restarted. Invalid structured data leaves the graph unchanged and returns a distinct, client-visible error. This endpoint is not exposed in the web viewer.
- FR56: The web frontend is a separate, independently buildable application from the Python package, within the same repository; a production build of it can be served by the backend API process.
- FR57: Loading structured data or documents is not exposed in the web viewer — `load-symbols`/`load-documents` stay CLI-only (FR55's reload endpoint is a distinct, narrower capability: reloading structured data into an already-running process, not a general-purpose loader UI).

### Domain-agnosticism guardrail

- FR17: The codebase enforces, via an automated check, that no domain-specific literal (e.g. tarot-specific terms) appears in the core library or CLI modules — domain content lives only in data files and test fixtures.

### Structured-data authoring ergonomics

These refine FR2–FR5: the underlying Sign Graph data model is unchanged by any of the following — they govern how a human curator *authors* structured data, not what the system stores.

- FR18: Structured-data files reference other entities (an intersemiotic interpretant's target sign, a citation's source, a manifestation's tradition) by human-readable name rather than requiring curators to invent and consistently repeat opaque slugs across files. An intersemiotic interpretant's target is resolved by name scoped to a named target semiotic system (`target_system`). The loader resolves names to the correct entity and reports a clear, actionable error on an unresolvable or ambiguous name, or on a target semiotic system with no matching sign, rather than guessing.
- FR19: An intersemiotic interpretant between two signs may be declared inline within the manifestation that asserts it, rather than requiring a separate relationship file — using the same attributable, multi-claim semantics as FR3 (competing claims from different traditions/attribution-systems still coexist without conflicting). Each intersemiotic interpretant names its target sign's semiotic system and name.
- FR20: A manifestation may carry a lightweight list of descriptive interpretants — thematic concepts, notable depicted elements, or other free-text tokens — that does not create a new sign or intersemiotic interpretant. This is distinct from FR3/FR19's intersemiotic interpretants, which are reserved for a target that itself carries independently-tracked, citable meaning; curators choose per case which is appropriate, and a descriptive interpretant can later be promoted to a full cross-referenced sign without any schema change.
- FR21: A sign may carry intrinsic, tradition-independent properties — facts true of the sign itself regardless of interpretive lens (e.g. a Hebrew letter's position in its alphabet or its numeric value). A manifestation may also carry its own tradition-scoped properties — structural facts specific to that one tradition's rendering (e.g. a card's position number within one specific deck). Properties, at either scope, are kept structurally distinct from a manifestation's interpretants (FR2), which can genuinely vary by tradition and are eligible for retrieval; a property is never used to build retrieval query text (FR8), regardless of scope.
- FR22: A sign is not required to have any manifestation to exist in the graph or to participate in an intersemiotic interpretant. Intersemiotic interpretants (FR3, FR19) are asserted between signs directly, not between specific manifestations of them, so a sign serving purely as an intersemiotic-interpretant target or structural anchor (e.g. a Tree of Life path or a sephirah referenced only as someone else's correspondence) never needs interpretive content written for it.

### Conversational agent

- FR58: The system provides an in-app conversational agent, served by the backend API and surfaced as a chat panel in the web viewer, that runs an interactive, multi-turn conversational session and answers successive user requests until the user ends the session.
- FR59: The agent answers each request by invoking one or more read-only tools and composing their results into a natural-language reply. It maintains conversation history across turns within a session.
- FR60: The agent has access to exactly these tools, each wrapping an existing service function and returning structured data (not prose):
  - **list semiotic systems** — the available semiotic systems.
  - **list traditions** — the available traditions, optionally scoped to one semiotic system.
  - **list symbols** — the available signs, optionally scoped to one semiotic system.
  - **get symbol** — retrieve one named sign's facts: its canonical name, semiotic system, intrinsic properties, and, for a given tradition, its manifestation's interpretants, denotation, correspondences, and citations. This is a graph-facts lookup, not a corpus retrieval — it runs no similarity search.
  - **query symbol** — run a region (hotspot) query for a given sign and tradition, returning ranked regions with their matched interpretants, verbatim segment text, and citations (the same operation as `GET /api/query`).
  - **fetch segments** — retrieve a contiguous ordinal range of one source's segments verbatim, by structural coordinate, running no similarity search (the same operation as `GET /api/segments`, FR82).
  - **summarize passage** — produce a single-turn summary of supplied passage text scoped to supplied interpretants, using the generation model (the same operation as `POST /api/summarize`).
- FR61: The registered tool set contains no operation that writes to, mutates, or reloads either store. Read-only is a structural property of the tool set, not a runtime check.
- FR62: When a request to list traditions or symbols, or to get or query a symbol, does not determine which semiotic system to use and the choice is ambiguous (more than one semiotic system exists and the request names none), the agent asks the user which semiotic system to use before listing or retrieving, rather than guessing or silently listing across all systems. Once a semiotic system is established in the conversation, the agent may reuse it for subsequent turns without re-asking.
- FR63: The agent must not state any symbol, interpretant, tradition, source, or passage as fact unless it appears in a tool result from the current session, and it must carry through the citation/locator the tool returned. It must not fabricate or infer symbols or interpretations absent from tool results.
- FR64: When the get-symbol tool returns `needs_tradition` (no interpretive content, only the sign's available traditions), the system presents the tradition choices to the user deterministically, without generation-model involvement. This guarantees FR63 cannot be violated in this specific case regardless of model behavior, since a tradition list is the entirety of what the tool returned and needs no model composition.
- FR65: The agent's generation model is a local Ollama model. When no generation model is configured or the model cannot be reached, the command reports a distinct, actionable error rather than proceeding.
- FR66: The retrieval a tool triggers invokes no generation model and is unchanged from the existing query path (FR29): the generation model is used only for the agent's own conversation/tool-selection and for the explicit summarize tool.
- FR67: Each turn surfaces a tool trace — which tools the agent called, in order — so the user can see the evidence path behind the answer.
- FR68: A tool that fails (e.g. an unknown sign or tradition, an unreachable model for summarization) returns a distinct error to the agent that the agent relays to the user, without terminating the session; the user can continue with further turns.
- FR69: The agent loop is bounded: a single turn cannot invoke tools indefinitely. On reaching the bound, the turn ends with a clear message rather than looping.
- FR70: The agent is additive and self-contained. It adds no command to the `mythrix` CLI; the existing `query`, `load-symbols`, and `load-documents` commands and all other `/api/*` routes are unchanged in behavior and output.

### Conversational agent chat panel

Refines FR58–FR70 for the panel's web-UI-specific behavior; the underlying agent loop, tool set, and orchestration boundary (ADR 0006) are unchanged.

- FR94: The chat panel is docked, floating, and has exactly two states — open and collapsed. Collapsing preserves the active thread; re-opening restores it unchanged. It never reflows the hotspot list, facets, or control panel.
- FR95: The panel is grounded in the currently active hotspot; a context strip displays that hotspot's structural reference and its matched interpretants at all times.
- FR96: Selecting a different hotspot starts a new thread (see Vocabulary): the prior thread's messages are replaced by a reset divider naming the new hotspot; threads are never merged or extended across hotspots. Changing a session-scoped context field via chat (a new sign or tradition) triggers the same reset. The backend, not the browser, detects the reset condition — by comparing the incoming turn's selection against the context it stored from the previous turn — and clears its per-thread working notes and message history before invoking the agent loop.
- FR97: Each user turn is sent with a context object: session-scoped fields (semiotic system, sign, tradition, facet/min-score selection) that persist across hotspot changes until explicitly changed, and thread-scoped fields (the active hotspot's structural reference and human-readable locator, FR101) that reset with the thread. The browser always sends its current selection as-is, never pre-clearing or diffing it; the backend returns an updated or confirmed-unchanged context alongside its reply. Fields fill in independently from either side — the UI's selection sets any of them directly, and the agent sets one when it resolves an entity from a chat message alone. The context object never carries passage or segment text; any verbatim text the agent needs is retrieved through its own tool calls.
- FR98: Whenever an attempted tool call needs a field that is still unset, the agent distinguishes ambiguous (more than one value is plausible — the tool call names its own candidates, and the clarifying question is composed directly from that result, with no generation-model call) from not yet determined (nothing has been selected or searched yet — the agent says so plainly, with no candidates to offer). This generalizes FR62/FR64's semiotic-system-specific and tradition-specific bypasses to any field capable of the same ambiguity; neither case ends with the agent guessing a value.
- FR99: Every structured element shown in the thread (a verse citation, a set of scored interpretant chips) is populated by the backend directly from the tool result(s) that grounded that turn — never parsed or inferred from the model's free-text reply.
- FR100: Thread and session history and context are retained only for the life of the browser session; none of it is persisted across a backend process restart.
- FR101: The context object's thread-scoped fields include the active hotspot's human-readable locator (e.g. "Ecclesiasticus 43:1-4") alongside its structural reference, giving the agent a ready citation to quote without a separate tool call purely to resolve it.
- FR102: The composer recognizes a `/clear` command: it is never sent to the agent or shown as a user message, and instead wipes the active thread and starts a new agent session, so the next turn carries no prior history or working notes.

### Hotspot context expansion

- FR71: The hotspot detail panel provides an **Add Context** action that loads additional verbatim segments from the same source as the hotspot and displays them interleaved, in structural (ordinal) order, with the hotspot's existing segments. Context segments are visually distinguished from matched segments.
- FR72: An activation first fills every remaining internal gap — each non-matching segment whose ordinal lies strictly between the current leading and trailing edges but is not yet loaded — so the loaded span reads as one contiguous, gap-free sequence of segments.
- FR73: When no internal gap remains, an activation extends the loaded span by one segment before the current leading edge and one segment after the current trailing edge, subject to FR74/FR75.
- FR74: When the source declares a chapter/section structure, each edge stops at its own chapter boundary: the leading edge never loads a segment from the previous chapter, and the trailing edge never loads a segment from the next chapter.
- FR75: When the source declares no chapter/section structure, each edge extends toward the source's first / last segment and stops there.
- FR76: The two edges advance independently. An activation extends every edge that can still extend; an edge already at its bound contributes nothing while the other edge continues. The action remains available while any edge can still extend or any internal gap remains.
- FR77: The action is disabled (and visibly indicates that no further context is available) once no internal gap remains and both edges have reached their bounds.
- FR79: Context is drawn only from the same source as the hotspot. Expansion never crosses into another source or another hotspot.
- FR80: Loaded context is scoped to the individual hotspot. Selecting a different hotspot presents that hotspot's own matched segments with no context carried over; a new query resets all expansion.
- FR81: Context segments display their verbatim text and structural locator with no client-side truncation, consistent with FR46/FR52. Interpretant chips continue to anchor to and scroll to their matched segments after context is loaded; context segments are never chip targets.
- FR82: The backend exposes retrieval of a source's segments by structural coordinate — a contiguous ordinal range within one source — returning each segment's verbatim text, structural locator, ordinal, and section, executed through the existing stores without running a similarity query. This is sufficient for the client to render context and to determine chapter boundaries (FR74) and source ends (FR75).
- FR83: A context-load request that fails returns a distinct, client-visible error without altering or clearing the displayed hotspot or the current query result.

### Tabbed workspace & redesign

- FR84: The web viewer holds one or more tabs at a time. Each tab owns, in isolation from every other tab: the selected semiotic system, symbol, tradition, and min-score override (FR50/FR53); the current query result, if any (FR51); the Sources/Interpretants facet selections and the interpretant-search filter text (FR51, FR91); and the selected hotspot (FR52). Changing any of these in one tab never affects another tab's state.
- FR85: A tab strip, in the top bar, lists every open tab in creation order and visually distinguishes the active tab. The user can: switch to any tab by selecting it; open a new, empty tab; and close any tab. Closing the only remaining open tab replaces it with a new, empty tab — the viewer always has at least one tab.
- FR86: A tab's displayed label reflects its own state: the queried symbol's name once that tab has a result, otherwise a placeholder indicating no query has run yet in that tab.
- FR87: A new tab starts with no system/symbol/tradition selected, no query result, and no facet selections — the same empty state the viewer has before a first query — never copying another tab's selections.
- FR88: The docked agent chat panel (FR58–FR70, FR94–FR102) is a single, shared dock (its collapsed/expanded state is not per-tab), but its grounding context and its message thread always reflect the active tab: the context strip shows the active tab's selected hotspot (or that none is selected), and the thread shown is that tab's own thread and no other's. Switching tabs switches which tab's context and thread the dock displays; it never merges two tabs' threads.
- FR89: Each tab has its own agent session (its own session id and its own conversation history/context, per FR97's per-session context state). A message sent from one tab is answered within that tab's own thread and session even if the user switches to a different tab before the reply arrives; the reply is appended to the originating tab's thread, not whichever tab happens to be active when it arrives.
- FR90: Closing a tab discards that tab's agent session and thread along with the rest of its state (FR84); it is not recoverable.
- FR91: The Interpretants facet (FR51) offers a text filter over the facet's own option labels; it narrows which interpretant options are listed, without changing the interpretant selection itself or any facet count. This filter text is part of a tab's own state (FR84).
- FR92: The web viewer's visual presentation follows a single, shared design system across the whole shell, including the agent panel: a warm color palette, a serif/sans/monospace type system, and a layout of a top bar (brand + tab strip), a control panel (query form + facets), a hotspot rail, and a hotspot detail reading pane, collapsing the control panel and detail pane into slide-over drawers below a defined viewport breakpoint. No functional requirement established elsewhere in this spec changes as a result of this restyling — every existing behavior (facet AND-filtering, hotspot navigation, Add Context, copy reference, agent chat) is preserved, only its presentation changes.
- FR93: The agent dock's visual design tokens are reconciled with the rest of the shell's tokens — it does not define its own, separate color palette.

### Retired requirements

- FR14, FR15, FR25, FR26: Retired — superseded by FR29 (no generation on the `query` path) and FR24/FR27 (per-concept retrieval and pair convergence replace synthesized summaries).
- FR54, FR78: Retired — the standalone on-demand "Generate AI summary" button and its panel-scoped behavior are removed; summarization is reachable through the conversational agent chat panel (FR58–FR70, FR94–FR102) as an ordinary chat request, using the same underlying summarization capability (FR60's summarize-passage tool).

## Structured-data authoring format (worked example)

A tarot card and a Hebrew letter, showing every mechanism above together:

```yaml
# data/semiotic_systems/tarot/signs/the-fool.yaml
semiotic_system: tarot
sign:
  name: "The Fool"
  type: major-arcana

  manifestations:
    - tradition: rider-waite
      display_name: "The Fool"
      denotation: >
        A man dressed in ragged, colorful jester-like clothes with small bells walks
        briskly across a rocky ground. He holds a walking stick in his right hand and
        carries a stick with a small pouch slung over his left shoulder. A quadruped
        animal resembling a small dog or cat tears at his trousers from behind, pulling
        them down to expose the flesh of his thigh and backside. He looks forward and
        slightly upward while walking, ignoring the animal entirely, and the space at
        the very top of the card contains no number.
      interpretants:
        - type: concept
          value: dog
        - type: concept
          value: white rose
        - type: concept
          value: cliff
      cites: "Waite, Pictorial Key to the Tarot, p. 97"
      intersemiotic_interpretants:
        - target_system: hebrew_alef_bet
          target_sign: "Samekh"
          relationship: hebrew_letter
          according_to: "Golden Dawn"
```

```yaml
# data/semiotic_systems/hebrew_alef_bet/signs/samekh.yaml
semiotic_system: hebrew_alef_bet
sign:
  name: "Samekh"
  type: hebrew-letter
  properties:
    - {key: alphabet_position, value: "15"}
    - {key: numeric_value, value: "60"}

  manifestations:
    - tradition: golden-dawn-kabbalah
      display_name: "Samekh (ס)"
      denotation: "Support and protection; the serpent encircling the initiate."
      intersemiotic_interpretants:
        - target_system: hebrew_alef_bet
          target_sign: "Path: Tiphareth–Yesod"
          relationship: tree_of_life_path
          according_to: "Golden Dawn"
        - target_system: hebrew_alef_bet
          target_sign: "Tiphareth"
          relationship: sephirah
          according_to: "Golden Dawn"
        - target_system: hebrew_alef_bet
          target_sign: "Yesod"
          relationship: sephirah
          according_to: "Golden Dawn"
```

Reading this against the FRs: `interpretants` (FR20) here holds depicted objects from the card's artwork ("dog", "white rose", "cliff") — no sign is created for any of them. `intersemiotic_interpretants` (FR19) references `"Samekh"` by name (FR18) scoped to its `target_system` (`hebrew_alef_bet`) rather than a pre-coordinated slug, and asserts a claim attributed to a specific tradition ("Golden Dawn"), so a competing attribution system could add a second, independent `intersemiotic_interpretants` entry for the same card without conflict (FR3). Samekh's `properties` (FR21) — alphabet position, numeric value — sit on the sign itself, not on its `golden-dawn-kabbalah` manifestation. `"Path: Tiphareth–Yesod"`, `"Tiphareth"`, and `"Yesod"` are referenced purely as intersemiotic-interpretant targets. Per FR18 the loader requires each to be declared in its own sign file, in the same semiotic system, before it can be referenced — but per FR22 that file needs nothing beyond a bare `semiotic_system:` and `sign:` block, e.g. `semiotic_system: hebrew_alef_bet` / `sign: {name: "Tiphareth", type: sephirah}`, with no `manifestations:` at all. Either can be enriched with a full manifestation later without changing anything that already references it.

## Reference implementation scope

The first reference dataset is tarot (starting with the Rider-Waite tradition). The v1 end-to-end proof is: load a small set of tarot signs/traditions/sources via the structured-data loader, load an excerpt of a public-domain primary source (e.g. Waite's *Pictorial Key to the Tarot*) via the document loader, then query a single sign (e.g. "The Tower") in that tradition via the CLI and receive ranked evidence: per-concept candidate passages plus their pair convergences (FR24/FR27), each with attribution and verbatim text (FR13).

`data/semiotic_systems/tarot/` holds one tradition (`rider-waite`), one source (`waite-pictorial-key`), and all 22 Major Arcana as signs (`data/semiotic_systems/tarot/signs/*.yaml`), each with a Rider-Waite manifestation. Each `denotation` (the card's visual description) is curator-authored, not quoted from Waite. Each `cites` locator points at that card's real section in his 1910 text, fetched from a public-domain digitization. `interpretants` are extracted from each card's `denotation` per FR20. Each card's intersemiotic interpretant names a Hebrew letter declared in `data/semiotic_systems/hebrew_alef_bet/`, its own sibling reference dataset.

The RAG document is not Waite's own text (see FR7 — an uploaded document is read through the graph's established symbolism, independent of any source a structured `Manifestation` was extracted from): `data/corpus/scripture/en_drb/` provides the complete Douay-Rheims Bible (Old and New Testament, public domain) as an independent corpus source — its `.yaml` (id, domain, citation label, bibliographic metadata) colocated with the raw `.txt` it describes, carrying no `Tradition` (FR6) — meant to be read *through* the tarot signs' established meanings rather than treated as their source. It declares a `scripture_verse` segmentation scheme (FR31), one segment per verse. `data/corpus/kabbalah/en_bahir/` provides the Sefer HaBahir as a second corpus source, declaring a `numbered_section` scheme, one segment per numbered section — proving segmentation is source-declared and corpus-agnostic, not scripture-specific.
