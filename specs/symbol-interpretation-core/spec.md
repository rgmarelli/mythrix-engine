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

## Goals

- A **domain-agnostic Sign Graph** data model representing signs, interpretive traditions, tradition-scoped manifestations, properties, interpretants, and intersemiotic interpretants (including cross-tradition, cross-domain, and alternative/competing claims), and sources — with no distinct meaning ever collapsing into another's, whether the distinction comes from tradition, from a competing attribution system, or from a nested context within a domain (e.g. a sign's manifestation within a specific sub-concept of its domain).
- A **RAG pipeline** grounded in curated primary-source documents, searched as one independent corpus rather than scoped by interpretive tradition.
- A **local-only pipeline** (no hosted API dependency) that returns ranked, cited evidence for a query — retrieved graph facts and source passages — rather than a generated narrative. Citation-validation machinery is retained for the planned conversational agent layer, which is where any generated text belongs.
- **Three tools sharing one core library**:
  - A CLI for querying/interpreting symbols.
  - A structured-data loader that populates the Sign Graph from human-authored data.
  - A document loader that ingests primary source texts into the RAG vector store.
- **Tarot as the first reference dataset**, used to prove a single-sign, single-tradition query end-to-end through the full pipeline (CLI → graph retrieval → document retrieval → ranked concept and concept-pair evidence, per FR27–FR29).

## Non-goals (v1)

- Multi-symbol or spread-style queries (e.g. interpreting several symbols together in one request).
- Cross-tradition comparison synthesis as a query capability — e.g. surfacing two *interpretive* traditions' competing readings of the same symbol (Crowley's vs. Waite's) side by side and adjudicating which one a document corpus better supports. The data model must support intersemiotic interpretants between traditions, but no query surface for comparing traditions ships in v1. (This is distinct from FR7 — retrieving from an independent, non-interpretive document corpus like a scriptural text through one tradition's established symbolism is in scope; comparing two competing interpretive traditions against each other is not.)
- Conversational or free-text natural-language request parsing — v1 uses structured CLI arguments only. A conversational agent layer (a console/chat interface driving an agent loop) is planned for a future version and must not be precluded by v1's design. The prompt-rendering, marker-enumeration, citation-validation, and Ollama-client modules exist for that layer; the v1 `query` path does not invoke them.
- Hardening against adversarial input / prompt injection beyond baseline mitigations (data-not-instructions framing, citation-id validation). Full adversarial hardening is deferred; v1 assumes curator-supplied, not arbitrary, source documents.
- Verifying that LLM paraphrases are faithful to their cited source, beyond confirming the citation marker refers to real, in-context material. Faithfulness/entailment checking is future work.
- Concurrent multi-process write access to the graph store or vector store.
- Sentiment analysis — not designed or scoped here; deferred to the conversational agent layer. Tracked as an open idea in `docs/TODO.md`, not a v1 deliverable.

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
- FR8: The text used to drive similarity search is derived from retrieved graph facts — an interpretant's `value`, never a sign's or manifestation's `properties`, and never a sign's canonical name or a manifestation's denotation, and never raw, unvalidated user input. This includes the whole graph reachable from the queried sign via `intersemiotic_interpretants` (FR3, FR19) — each target sign's own interpretants are folded into the query too, but never the target's properties. An interpretant carrying a `query.directive: "filter"` annotation is excluded from the plain query text and is instead applied as an additional literal-text filter using its `query.as_token` value, alongside — never instead of — every other interpretant's plain query.
- FR23: The document loader computes a content hash of each ingested source file and records it on the corresponding `Source`. Re-running the loader with an unchanged file is a no-op (idempotent, no duplicate chunks); re-running with a changed file replaces that source's previously ingested chunks rather than accumulating stale ones alongside the new content.

### Query / synthesis

- FR9: A query names one sign and one tradition (v1 scope) and returns evidence grounded in (a) deterministic graph retrieval and (b) document retrieval across the full corpus, organized per concept (FR24) and per concept pair (FR27).
- FR10: Graph retrieval is deterministic and code-driven — the system never asks an LLM to generate a graph query from user input.
- FR11: Retrieval and ranking are entirely code-driven; no model participates in deciding what a result *is*. (Applies to the planned agent layer as well as the `query` path.)
- FR12: Any generated text the system produces carries a citation marker for every substantive claim, and the system validates in code that each marker refers to material actually present in the retrieved context, rejecting or flagging markers that don't. The `query` path produces no generated text, so this requirement currently governs only the planned agent layer; the validation code exists and is exercised by it.
- FR13: For every cited document source, the output includes the source's citation label and the verbatim retrieved passage/paragraph text itself — not merely a citation marker or locator. This applies to both human-readable and JSON output.
- FR16: The CLI supports a structured (JSON) output mode capturing the full evidentiary chain — graph fact identifiers, retrieved chunk identifiers/offsets, retrieved passage text, the embedding model identifier used, and per-concept-pair membership and match scores (FR27) — so a result is reproducible and auditable even after the corpus or models change later. Every `Source`/`Tradition` referenced anywhere in the result is listed once under top-level `sources`/`traditions` tables keyed by id, with passages/manifestations referencing them by `source_id`/`tradition_id` rather than embedding the full object per citation. Marker numbering is the 1-based position within each list.

### Concept-scoped retrieval

- FR24: Retrieval is organized per concept — each individually-queried graph fact (an interpretant's value, or an intersemiotic interpretant's target interpretant, per FR8's query decomposition) retrieves its own candidate passages independently, rather than every query's hits being merged into one shared pool before any cutoff is applied. Each concept gets its own retrieval budget.

### Concept-pair convergence

- FR27: Where two concepts both retrieve the same passage, the system emits an additional result group keyed by that concept pair, ranked independently and displayed alongside — never instead of — the per-concept groups of FR24. Pair membership is detected against a retrieval pool deeper than the one displayed. A passage matched by three or more concepts appears in each of its constituent pairs. Each pair result carries a combined match score derived from the underlying similarity scores rather than from ordinal rank, together with the per-concept component scores it was derived from.
- FR28: An interpretant carrying a `query.directive: "filter"` annotation (FR8) appears as a first-class member of a pair alongside semantic concepts, so a result can read as "child + 100". Such an interpretant reaches a passage through a literal text filter rather than through embedding similarity: its membership is a guarantee that the passage contains its `query.as_token` text, not a similarity judgement. It contributes membership but no score; a pair combining one semantic concept with one exact-filter interpretant is scored by the semantic concept alone.
- FR29: The query path invokes no generation model. Answering a query requires the embedding model only.

### Domain-agnosticism guardrail

- FR17: The codebase enforces, via an automated check, that no domain-specific literal (e.g. tarot-specific terms) appears in the core library or CLI modules — domain content lives only in data files and test fixtures.

### Structured-data authoring ergonomics

These refine FR2–FR5: the underlying Sign Graph data model is unchanged by any of the following — they govern how a human curator *authors* structured data, not what the system stores.

- FR18: Structured-data files reference other entities (an intersemiotic interpretant's target sign, a citation's source, a manifestation's tradition) by human-readable name rather than requiring curators to invent and consistently repeat opaque slugs across files. An intersemiotic interpretant's target is resolved by name scoped to a named target semiotic system (`target_system`). The loader resolves names to the correct entity and reports a clear, actionable error on an unresolvable or ambiguous name, or on a target semiotic system with no matching sign, rather than guessing.
- FR19: An intersemiotic interpretant between two signs may be declared inline within the manifestation that asserts it, rather than requiring a separate relationship file — using the same attributable, multi-claim semantics as FR3 (competing claims from different traditions/attribution-systems still coexist without conflicting). Each intersemiotic interpretant names its target sign's semiotic system and name.
- FR20: A manifestation may carry a lightweight list of descriptive interpretants — thematic concepts, notable depicted elements, or other free-text tokens — that does not create a new sign or intersemiotic interpretant. This is distinct from FR3/FR19's intersemiotic interpretants, which are reserved for a target that itself carries independently-tracked, citable meaning; curators choose per case which is appropriate, and a descriptive interpretant can later be promoted to a full cross-referenced sign without any schema change.
- FR21: A sign may carry intrinsic, tradition-independent properties — facts true of the sign itself regardless of interpretive lens (e.g. a Hebrew letter's position in its alphabet or its numeric value). A manifestation may also carry its own tradition-scoped properties — structural facts specific to that one tradition's rendering (e.g. a card's position number within one specific deck). Properties, at either scope, are kept structurally distinct from a manifestation's interpretants (FR2), which can genuinely vary by tradition and are eligible for retrieval; a property is never used to build retrieval query text (FR8), regardless of scope.
- FR22: A sign is not required to have any manifestation to exist in the graph or to participate in an intersemiotic interpretant. Intersemiotic interpretants (FR3, FR19) are asserted between signs directly, not between specific manifestations of them, so a sign serving purely as an intersemiotic-interpretant target or structural anchor (e.g. a Tree of Life path or a sephirah referenced only as someone else's correspondence) never needs interpretive content written for it.

### Retired requirements

- FR14, FR15, FR25, FR26: Retired — superseded by FR29 (no generation on the `query` path) and FR24/FR27 (per-concept retrieval and pair convergence replace synthesized summaries).

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

The RAG document is not Waite's own text (see FR7 — an uploaded document is read through the graph's established symbolism, independent of any source a structured `Manifestation` was extracted from): `data/corpus/scripture/en_drb/` provides the complete Douay-Rheims Bible (Old and New Testament, public domain) as an independent corpus source — its `.yaml` (id, domain, citation label, bibliographic metadata) colocated with the raw `.txt` it describes, carrying no `Tradition` (FR6) — meant to be read *through* the tarot signs' established meanings rather than treated as their source.
