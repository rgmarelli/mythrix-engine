# Symbol Interpretation Core — Spec

## Problem

Existing symbolic-interpretation tools fall into two unsatisfying categories: opaque divinatory black boxes that offer no reasoning trail, or unstructured LLM wrappers that generate plausible-sounding but invented interpretations. Researchers and practitioners working in comparative symbolism, digital humanities, and related fields need a tool where every conclusion is traceable back to (a) the specific symbols identified, (b) the primary sources retrieved, and (c) the reasoning chain connecting them — with interpretive traditions kept distinct rather than blended into one composite "meaning."

## Goals

- A **domain-agnostic Symbol Graph** data model representing symbols, interpretive traditions, tradition-scoped interpretations, attributes, relationships (including cross-tradition, cross-domain, and alternative/competing relationships), and sources — with no distinct meaning ever collapsing into another's, whether the distinction comes from tradition, from a competing attribution system, or from a nested context within a domain (e.g. a symbol's manifestation within a specific sub-concept of its domain).
- A **RAG pipeline** grounded in curated primary-source documents, with retrieval scoped by interpretive tradition.
- A **local-only LLM synthesis step** (no hosted API dependency) that explains retrieved graph facts and source passages, producing citations that are validated in code rather than merely requested by prompt.
- **Three tools sharing one core library**:
  - A CLI for querying/interpreting symbols.
  - A structured-data loader that populates the Symbol Graph from human-authored data.
  - A document loader that ingests primary source texts into the RAG vector store.
- **Tarot as the first reference dataset**, used to prove a single-symbol, single-tradition query end-to-end through the full pipeline (CLI → graph retrieval → document retrieval → LLM synthesis with citations).

## Non-goals (v1)

- Multi-symbol or spread-style queries (e.g. interpreting several symbols together in one request).
- Cross-tradition comparison synthesis as a query capability — e.g. surfacing two *interpretive* traditions' competing readings of the same symbol (Crowley's vs. Waite's) side by side and adjudicating which one a document corpus better supports. The data model must support cross-tradition relationships, but no query surface for comparing traditions ships in v1. (This is distinct from FR7 — retrieving from an independent, non-interpretive document corpus like a scriptural text through one tradition's established symbolism is in scope; comparing two competing interpretive traditions against each other is not.)
- Conversational or free-text natural-language request parsing — v1 uses structured CLI arguments only. A conversational agent layer is planned for a future version and must not be precluded by v1's design.
- Hardening against adversarial input / prompt injection beyond baseline mitigations (data-not-instructions framing, citation-id validation). Full adversarial hardening is deferred; v1 assumes curator-supplied, not arbitrary, source documents.
- Verifying that LLM paraphrases are faithful to their cited source, beyond confirming the citation marker refers to real, in-context material. Faithfulness/entailment checking is future work.
- Concurrent multi-process write access to the graph store or vector store.

## Functional requirements

### Symbol Graph (structured data)

- FR1: The system represents `Symbol`, `Tradition`, `Interpretation` (a symbol as understood within one tradition), `Attribute`, and `Source` as distinct entities, with no domain-specific fields baked into the core schema.
- FR2: A symbol may have multiple `Interpretation`s, one per tradition, each with its own display name/title (a symbol's name is not assumed to be tradition-invariant — e.g. the same tarot card may be titled differently across traditions), summary, attributes, and citations, all scoped to that interpretation only.
- FR3: Relationships between interpretations (including across traditions, across domains — e.g. a tarot symbol related to a Kabbalah symbol — and across nested sub-contexts within a domain, e.g. a concept that manifests distinctly within each of several parallel contexts such as a sephirah within a given "world") are first-class, typed (a free-text relationship type, not a fixed enum), and attributable: each relationship claim records which tradition/attribution-system asserts it and may cite a source, so multiple alternative or competing claims can coexist for the same symbol without conflicting or silently overwriting one another. No domain-specific structural concepts (such as a fixed notion of "world" or "level") are introduced into the core schema — nested contexts are represented as ordinary data using the same symbol/interpretation/relationship primitives.
- FR4: The structured-data loader accepts human-authored, version-controllable source files, validates their schema and referential integrity (e.g. a citation must reference an already-loaded source; a relationship must reference existing symbol/tradition pairs) before writing anything, and upserts idempotently — re-running the loader on edited data does not create duplicates.
- FR5: Invalid or referentially inconsistent structured data is rejected with an actionable error, not silently partially loaded.

### Document corpus (RAG)

- FR6: The document loader ingests primary source texts, chunks them, embeds them via the local embedding model, and stores them with metadata sufficient to filter by tradition/domain and to reconstruct a human-readable citation (source title, author, locator).
- FR7: Retrieval at query time searches the full ingested document corpus by default, not just documents tagged under the queried symbol's own tradition — an uploaded document (e.g. a scriptural or literary text) is an independent corpus to be read *through* the graph's established symbolism, not a competing interpretation that must be kept separate from it, so it is never excluded from retrieval just because it carries a different tradition tag. This is distinct from comparing multiple *interpretive* traditions of the same symbol against each other (e.g. deciding whether Crowley's or Waite's reading of a card is "more correct"), which remains out of scope for v1 (see Non-goals) — should a second interpretive tradition's own commentary be added later, retrieval will need an explicit scoping mechanism to avoid blending competing interpretations together, which does not exist yet (see plan.md Risks).
- FR8: The text used to drive similarity search is derived from retrieved graph facts (canonical name, attributes, summary), not from raw, unvalidated user input. This includes the whole graph reachable from the queried symbol via `corresponds_to` (FR3, FR19) — each relationship target's own name and semantic (non-ordinal) properties are folded into the query too, so a symbol's correspondences shape what gets retrieved, not just its own attributes. **Revised (post-T24 expansion):** originally this meant only the symbol's own attributes; extended after real usage showed a card's Hebrew-letter correspondence (meaning, assignation) had zero influence on retrieval despite being a graph fact the LLM was shown. "Semantic" is decided by `Attribute.value_type`: any attribute/property tagged `value_type: integer` (an ordinal or numeric-identity fact, e.g. a card's position number or a letter's gematria value) is excluded from the query text — it would inject an arbitrary numeral into the embedding rather than content related to meaning.
- FR23: The document loader computes a content hash of each ingested source file and records it on the corresponding `Source`. Re-running the loader with an unchanged file is a no-op (idempotent, no duplicate chunks); re-running with a changed file replaces that source's previously ingested chunks rather than accumulating stale ones alongside the new content.

### Query / synthesis

- FR9: A query names one symbol and one tradition (v1 scope) and returns an interpretation grounded in (a) deterministic graph retrieval and (b) tradition-scoped document retrieval.
- FR10: Graph retrieval is deterministic and code-driven — the system never asks an LLM to generate a graph query from user input.
- FR11: The LLM's role is limited to explaining/synthesizing already-retrieved facts and passages; it does not decide what the facts are.
- FR12: Every substantive claim in synthesized output carries a citation marker, and the system validates in code that each marker refers to material actually present in the retrieved context, rejecting or flagging markers that don't.
- FR13: For every cited document source, the output includes the source's attribution (title, author) and the verbatim retrieved passage/paragraph text itself — not merely a citation marker or locator — so a researcher can verify a claim against the actual source text without leaving the tool. This applies to both human-readable and JSON output.
- FR14: The CLI supports a facts-only mode that returns retrieved graph facts and passages without invoking the LLM (for auditing/debugging and for use without a running local LLM).
- FR15: The CLI supports a strict mode where a citation-validation failure is a hard error (non-zero exit) rather than a soft warning.
- FR16: The CLI supports a structured (JSON) output mode capturing the full evidentiary chain — graph fact identifiers, retrieved chunk identifiers/offsets, retrieved passage text, and the embedding/generation model identifiers used — so a result is reproducible and auditable even after the corpus or models change later.

### Domain-agnosticism guardrail

- FR17: The codebase enforces, via an automated check, that no domain-specific literal (e.g. tarot-specific terms) appears in the core library or CLI modules — domain content lives only in data files and test fixtures.

### Structured-data authoring ergonomics

These refine FR2–FR5: the underlying Symbol Graph data model is unchanged by any of the following — they govern how a human curator *authors* structured data, not what the system stores.

- FR18: Structured-data files reference other entities (a relationship's target, a citation's source, an interpretation's tradition) by human-readable name rather than requiring curators to invent and consistently repeat opaque slugs across files. The loader resolves names to the correct entity and reports a clear, actionable error on an unresolvable or ambiguous name rather than guessing.
- FR19: A correspondence between two symbols may be declared inline within the interpretation that asserts it, rather than requiring a separate relationship file — using the same attributable, multi-claim semantics as FR3 (competing claims from different traditions/attribution-systems still coexist without conflicting).
- FR20: An interpretation may carry a lightweight list of descriptive keywords — thematic concepts, notable depicted elements, or other free-text tags — that does not create a new symbol or graph relationship. This is distinct from FR3/FR19's cross-symbol relationships, which are reserved for a target that itself carries independently-tracked, citable meaning; curators choose per case which is appropriate, and a keyword can later be promoted to a full cross-referenced symbol without any schema change.
- FR21: A symbol may carry intrinsic, tradition-independent properties — facts true of the symbol itself regardless of interpretive lens (e.g. a Hebrew letter's position in its alphabet or its numeric value) — kept structurally distinct from an interpretation's tradition-scoped attributes (FR2), which can genuinely vary by tradition.
- FR22: A symbol is not required to have any interpretation to exist in the graph or to participate in a correspondence. Correspondences (FR3, FR19) are asserted between symbols directly, not between specific interpretations of them, so a symbol serving purely as a correspondence target or structural anchor (e.g. a Tree of Life path or a sephirah referenced only as someone else's correspondence) never needs interpretive content written for it.

## Structured-data authoring format (worked example)

A tarot card and a Hebrew letter, showing every mechanism above together:

```yaml
# data/tarot/symbols/the-fool.yaml
symbol:
  name: "The Fool"
  type: major-arcana

interpretations:
  - tradition: rider-waite
    display_name: "The Fool"
    summary: >
      A man dressed in ragged, colorful jester-like clothes with small bells walks
      briskly across a rocky ground. He holds a walking stick in his right hand and
      carries a stick with a small pouch slung over his left shoulder. A quadruped
      animal resembling a small dog or cat tears at his trousers from behind, pulling
      them down to expose the flesh of his thigh and backside. He looks forward and
      slightly upward while walking, ignoring the animal entirely, and the space at
      the very top of the card contains no number.
    keywords: [dog, white rose, cliff]
    cites: "Waite, Pictorial Key to the Tarot, p. 97"
    corresponds_to:
      - to: "Samekh"
        relationship: hebrew_letter
        according_to: "Golden Dawn"
```

```yaml
# data/kabbalah/symbols/samekh.yaml
symbol:
  name: "Samekh"
  type: hebrew-letter
  properties:
    - {key: alphabet_position, value: 15}
    - {key: numeric_value, value: 60}

interpretations:
  - tradition: golden-dawn-kabbalah
    display_name: "Samekh (ס)"
    summary: "Support and protection; the serpent encircling the initiate."
    corresponds_to:
      - to: "Path: Tiphareth–Yesod"
        relationship: tree_of_life_path
        according_to: "Golden Dawn"
      - to: "Tiphareth"
        relationship: sephirah
        according_to: "Golden Dawn"
      - to: "Yesod"
        relationship: sephirah
        according_to: "Golden Dawn"
```

Reading this against the FRs: `keywords` (FR20) here holds depicted objects from the card's artwork ("dog", "white rose", "cliff") — no graph entity is created for any of them. `corresponds_to` (FR19) references `"Samekh"` by name (FR18) rather than a pre-coordinated slug, and asserts a claim attributed to a specific tradition ("Golden Dawn"), so a competing attribution system could add a second, independent `corresponds_to` entry for the same card without conflict (FR3). Samekh's `properties` (FR21) — alphabet position, numeric value — sit on the symbol itself, not on its `golden-dawn-kabbalah` interpretation, because they'd be true under any tradition that discusses Samekh at all. `"Path: Tiphareth–Yesod"`, `"Tiphareth"`, and `"Yesod"` are referenced purely as correspondence targets. Per FR18 the loader still requires each to be declared in its own symbol file before it can be referenced (no silently guessing or auto-creating an unresolvable name) — but per FR22 that file needs nothing beyond a bare `symbol:` block, e.g. `symbol: {name: "Tiphareth", type: sephirah}`, with no `interpretations:` at all. Either can be enriched with a full interpretation later without changing anything that already references it.

## Reference implementation scope

The first reference dataset is tarot (starting with the Rider-Waite tradition). The v1 end-to-end proof is: load a small set of tarot symbols/traditions/sources via the structured-data loader, load an excerpt of a public-domain primary source (e.g. Waite's *Pictorial Key to the Tarot*) via the document loader, then query a single symbol (e.g. "The Tower") in that tradition via the CLI and receive a cited, grounded interpretation.

**Implemented (T24, expanded post-T24):** `data/tarot/` holds one tradition (`rider-waite`), one source (`waite-pictorial-key`), and all 22 Major Arcana as symbols (`data/tarot/symbols/*.yaml`), each with a Rider-Waite interpretation. Each `summary` (the card's visual description) is curator-authored, not quoted from Waite — his own write-up per card is interpretive commentary (Part II, "The Doctrine Behind the Veil") rather than a physical description of the artwork in most cases — and each `cites` locator points at that card's real section in his 1910 text, fetched from a public-domain digitization rather than paraphrased from memory. `keywords` are extracted from each card's `summary` per FR20. Correspondences (e.g. to a Hebrew letter/Tree of Life path) are deliberately left out of this dataset — nothing in "Reference implementation scope" requires them, and adding one would mean sourcing and verifying another factual attribution beyond what's needed to prove the pipeline end-to-end.

The RAG document is deliberately *not* Waite's own text (see FR7's revision below on why an uploaded document must be independent of the source a structured `Interpretation` was extracted from): `data/bible/` provides the complete Douay-Rheims Bible (Old and New Testament, public domain) as an independent corpus, tagged under its own `douay-rheims` tradition, meant to be read *through* the tarot symbols' established meanings rather than treated as their source.
