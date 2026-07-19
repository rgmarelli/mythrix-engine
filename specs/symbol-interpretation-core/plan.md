# Symbol Interpretation Core — Plan

Technical approach for the requirements in `spec.md`. This is a from-scratch design for an empty repo — no existing code is being modified.

## Package layout

Package name `mythrix`, `src/`-layout, `pyproject.toml` at repo root.

```
pyproject.toml
src/
  mythrix/
    core/                        # DOMAIN-AGNOSTIC. No tarot (or any domain) literals allowed here.
      models.py                  # Symbol, Tradition, Interpretation, Attribute, Source,
                                  # RelationshipFact, RetrievedPassage, GraphFacts,
                                  # RetrievalContext, Citation, InterpretationResult
      config.py                  # kuzu_db_path, chroma_dir, ollama_base_url,
                                  # embedding_model, generation_model, retrieval_top_k, ...
      errors.py                  # SymbolNotFoundError, TraditionNotFoundError,
                                  # IngestValidationError, CitationValidationError, ...
      graph/
        schema.py                # Kuzu DDL — single source of truth for the schema
        store.py                 # KuzuGraphStore: deterministic, parametrized queries only
      vector/
        store.py                 # ChromaVectorStore: add_documents(), similarity_search(filters)
        chunking.py               # chunking strategy, Chunk model
      retrieval/
        pipeline.py               # RetrievalPipeline: GraphFacts -> Chroma filter/query -> RetrievalContext
      synthesis/
        prompts.py                 # domain-agnostic prompt templates
        chain.py                   # LangChain LCEL chain: prompt | ChatOllama | citation validator
        citations.py               # citation-marker formatting + post-hoc validation
      loaders/
        symbol_schema.py           # pydantic models mirroring the YAML authoring format
        symbol_loader.py           # validates + idempotently upserts YAML into KuzuGraphStore
        document_loader.py         # reads source docs, chunks, embeds, upserts into Chroma
    cli/
      main.py                      # `mythrix` entrypoint (Typer), registers subcommands
      commands/
        query.py
        load_symbols.py
        load_documents.py
      formatting.py                # shared human-readable + --json renderers
data/
  tarot/                          # reference dataset — content only, never imported by mythrix.core
    traditions/rider-waite.yaml
    sources/waite-pictorial-key.yaml
    symbols/the-fool.yaml          # correspondences declared inline (FR19) — no relationships/ dir needed
    documents/waite-pictorial-key-to-the-tarot.txt
  kabbalah/
    traditions/golden-dawn-kabbalah.yaml
    symbols/samekh.yaml            # intrinsic properties (FR21) + its own tradition-scoped interpretation
tests/
  unit/
  integration/                    # opt-in, requires a running Ollama
  fixtures/tarot/
```

**Domain-agnostic boundary**: `src/mythrix/core/**` and `src/mythrix/cli/**` must never contain a tarot/Kabbalah/etc. literal — no `Suit` enum, no `arcana_number` field. All domain content lives in `data/**` or `tests/fixtures/**`. Enforced by an automated test (`tests/unit/test_domain_agnosticism.py`) that greps `core/`/`cli/` for a deny-list of domain terms — this satisfies FR17 and catches drift immediately rather than after a v2 domain is added.

The future conversational-agent requirement is satisfied structurally: `RetrievalPipeline.retrieve()` and the synthesis chain take already-structured `GraphFacts`/`RetrievalContext` objects, not raw CLI argv or free text. A future agent only needs to produce those structured inputs, not touch retrieval/synthesis internals.

## Kùzu graph schema

`Interpretation` is the key join entity — "this Symbol as understood within this Tradition" — which is what prevents distinct traditions' *meanings* from ever collapsing into one. Tradition-specific meaning (display name, summary, attributes, citations) hangs off `Interpretation`; correspondences between symbols (`RELATES_TO`) hang directly off `Symbol` instead — see below for why.

Node tables: `Symbol(id, slug, canonical_name, symbol_type, notes)` — `canonical_name` is an internal/fallback label only, never assumed to be the correct display name for any given tradition; `Tradition(id, slug, name, domain, description)`; `Interpretation(id, symbol_id, tradition_id, display_name, summary, created_at)` (id deterministically `symbol_slug::tradition_slug`) — `display_name` is the tradition-specific title actually shown to users (e.g. "Lust" vs. "The Force" for the same underlying card); `Attribute(id, key, value, value_type, position)`; `Source(id, title, author, publication_year, license, uri, content_hash, ingested_at)` — the last two are written by the document loader, not authored in a `Source` YAML file (FR23; see "Chroma vector store design").

Rel tables: `HAS_INTERPRETATION(Symbol -> Interpretation)`, `INTERPRETED_IN(Interpretation -> Tradition)`, `HAS_ATTRIBUTE(Symbol -> Attribute, Interpretation -> Attribute)`, `CITES(Interpretation -> Source, locator)`, `RELATES_TO(Symbol -> Symbol, relationship_type, description, symmetric, confidence, according_to_tradition_id, source_id)`.

**Symbol-intrinsic properties vs. tradition-scoped attributes (FR21).** `HAS_ATTRIBUTE` is a multi-pair rel table spanning both `Symbol -> Attribute` and `Interpretation -> Attribute` — verified to disambiguate cleanly by node type in a single query pattern (`tests/unit/test_graph_schema.py::test_has_attribute_spans_both_symbol_and_interpretation`). A Hebrew letter's alphabet position or numeric value is true regardless of which tradition discusses it, so it hangs off the bare `Symbol` (`Symbol.properties` in `core/models.py`, populated via `KuzuGraphStore._get_symbol_properties`); an interpretive claim like `element` or `keywords` can genuinely vary by tradition, so it stays on `Interpretation` (`Interpretation.attributes`, unchanged from the original design). Both reuse the same `Attribute` node table and the same `_upsert_attribute`/`_fetch_attributes` code in `store.py` — only the edge's source node differs.

**`RELATES_TO` connects `Symbol -> Symbol` directly (FR3, FR22)**, not `Interpretation -> Interpretation` as originally designed — cross-tradition/cross-domain links (tarot card → Kabbalah path) still fall out naturally without extra scoping fields, but a symbol with zero interpretations can now be a valid endpoint too, since there's no `Interpretation` node required for the edge to attach to. `according_to_tradition_id` is what carries the claim's attribution (e.g. a Hebrew-letter attribution system, assignable independently of which tarot-deck tradition a card belongs to); `source_id` is an optional citation for that specific claim. Kùzu permits multiple edges of the same rel table between the same node pair (empirically verified against the pinned version, see Risks and `tests/unit/test_kuzu_multi_edge_risk.py`), so alternative/competing claims for the same symbol coexist as separate `RELATES_TO` edges rather than overwriting each other. `Symbol.relationships` (in `core/models.py`) holds these; relationship targets are fetched shallow (their own `relationships` always `()`) to avoid unbounded recursion through `RelationshipFact.target_symbol`.

**Representing nested/compound contexts.** Some symbolic systems distinguish a concept's character across parallel sub-contexts of a domain — e.g. in Kabbalah, a sephirah takes on a genuinely different character within each of the Four Worlds, and Minor Arcana cards correspond to a specific (sephirah, world) pairing rather than to a sephirah in the abstract; Figure/court cards correspond similarly to a (partzuf, world) pairing. This requires no core schema change: the context (e.g. a "world") is modeled as an ordinary `Symbol`, and each nested manifestation (e.g. "Chesed of Atzilut") is its own `Symbol` with its own `Interpretation`(s), related back to the abstract concept via `RELATES_TO` (`relationship_type: manifestation_of`) for taxonomic grouping and to its context via another edge (`relationship_type: belongs_to_world`). This keeps meanings from collapsing across nested contexts the same way `Interpretation` keeps them from collapsing across traditions, and validates that the schema generalizes to multi-level correspondence systems (Major Arcana → Hebrew letter → path; Minor Arcana → sephirah-of-a-world; Figures → partzuf-of-a-world) purely through data — no domain-specific structural concept ever enters `core`.

Retrieval is always parametrized Cypher executed from plain Python. Original illustrative sketch (superseded — see "As implemented" note just below, and note `RELATES_TO` here predates its move to `Symbol -> Symbol`):

```python
conn.execute(
    """
    MATCH (s:Symbol {slug: $symbol_slug})-[:HAS_INTERPRETATION]->(i:Interpretation)
          -[:INTERPRETED_IN]->(t:Tradition {slug: $tradition_slug})
    OPTIONAL MATCH (i)-[:HAS_ATTRIBUTE]->(a:Attribute)
    OPTIONAL MATCH (s)-[r:RELATES_TO]->(s2:Symbol)
    OPTIONAL MATCH (i)-[:CITES]->(src:Source)
    RETURN s, i, collect(DISTINCT a), collect(DISTINCT {rel: r, symbol: s2}),
           collect(DISTINCT src)
    """,
    parameters={"symbol_slug": symbol_slug, "tradition_slug": tradition_slug},
)
```

User-facing values only ever flow through `parameters=`, never string-formatted into query text — the concrete implementation of FR10 at the retrieval layer.

**As implemented (T9):** rather than one aggregate query with nested `collect(...)` structs as sketched above, `KuzuGraphStore.get_interpretation()` composes several small, focused parametrized queries in Python (symbol lookup, tradition lookup, the interpretation itself, then attributes/citations/relationships each via their own query). This is simpler to test per-step and avoids depending on Cypher struct-collection behavior not exercised anywhere else in the codebase; the anti-hallucination property (FR10) is unchanged since every query is still parametrized and code-driven.

## Structured-data YAML format

**Revised from the original file-per-relationship design after review: the initial format normalized too closely to the graph's own shape (separate relationship files, manual `from`/`to` slug pairs, pre-declared slugs) — a human curator doesn't think that way.** The format below (FR18–FR21) is authored around one symbol at a time, referencing everything else by name.

One file per symbol/tradition/source under `data/<domain>/{traditions,sources,symbols}/`, loaded in dependency order: traditions → sources → symbols. There is no required `relationships/` directory in the common case — correspondences are declared inline, inside the interpretation that asserts them (FR19).

Example symbol file — a tarot card, showing `keywords` (FR20) and an inline `corresponds_to` claim (FR19) referencing another symbol by name (FR18):

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

Example symbol file — a Hebrew letter, showing intrinsic `properties` (FR21) kept separate from its tradition-scoped interpretation, and correspondences to symbols that have no interpretation of their own (FR22):

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

`"Path: Tiphareth–Yesod"`, `"Tiphareth"`, and `"Yesod"` each still need their own symbol file per FR18 (the loader errors on an unresolvable name rather than guessing) — but per FR22 that file is just a bare `symbol:` block, no `interpretations:` required, e.g.:

```yaml
# data/kabbalah/symbols/tiphareth.yaml
symbol:
  name: "Tiphareth"
  type: sephirah
```

A second, competing attribution for the same card would just add another `corresponds_to` entry with a different `according_to` (and possibly a different `to`) — no separate file, same mechanism as the Kaf/Teth example discussed during design, still backed by the same `RELATES_TO` multi-claim semantics (FR3).

**Loader responsibilities (`symbol_schema.py` + `symbol_loader.py`, T10/T11):** pydantic models (`TraditionFile`, `SourceFile`, `SymbolFile`) validate structure first. The loader then, per symbol file: (1) upserts the `Symbol` node (via `KuzuGraphStore.upsert_symbol`, or `upsert_symbol_with_interpretation` when the file has at least one interpretation), including any `properties` as `Symbol`-scoped `Attribute`s (FR21); (2) upserts one `Interpretation` per `interpretations[]` entry (with its `display_name`), using a deterministic `symbol_slug::tradition_slug` id derived from the human-provided `name`/`tradition`, when present — an `interpretations:` key is entirely optional (FR22); (3) expands `keywords` into `Interpretation`-scoped `Attribute`s with `key: "keyword"` (FR20) — no graph relationship or new symbol is created; (4) resolves `cites` and every `corresponds_to` entry's `to`/`according_to` by **name** against already-loaded symbols/traditions (FR18), raising `IngestValidationError` with the unresolved or ambiguous name on failure — nothing is written until every reference in the file resolves; (5) writes each `corresponds_to` entry as a `RELATES_TO` edge directly between the two **symbols** (FR19, FR22 — not between specific interpretations of them), scoped by the resolved `according_to_tradition_id`, so multiple claims about the same symbol coexist rather than overwrite each other. Name resolution and disambiguation (FR18) is new loader logic with its own test coverage requirement, distinct from the graph-level idempotency already verified in T9.

**Verified during implementation (T9):** Kùzu's `MERGE ... ON CREATE SET ... ON MATCH SET ...` is idempotent by key against the pinned version — re-running an upsert with identical data updates in place rather than duplicating, and a `RELATES_TO` `MERGE` keyed on `(relationship_type, according_to_tradition_id)` correctly adds a new parallel edge for a genuinely different claim while updating an existing one in place otherwise. No custom exists-then-insert/update logic was needed, contrary to what this section originally anticipated (see `KuzuGraphStore` in `core/graph/store.py` and `tests/unit/test_graph_store.py`). Satisfies FR2, FR3, FR4, FR5, FR18, FR19, FR20, FR21.

**Fixed during T24 (real-data bug, not a hypothetical).** `_resolve_citation`'s original "split on the *last* comma" rule silently misparsed a locator that itself contained a comma — e.g. `"Waite, Pictorial Key to the Tarot, Part II: The Doctrine Behind the Veil, XVI. The Tower"` (the real citation authored for `data/tarot/symbols/the-tower.yaml`) would have had the last comma's tail (`" XVI. The Tower"`) treated as the locator and everything before it, including the actual title, folded into the source query — which then failed to resolve at all, since `"Part II: The Doctrine Behind the Veil"` isn't part of any source's title/author. Fixed by always treating the *first two* comma-separated segments as the source reference (author, title) and everything after the second comma — untouched, commas and all — as the locator; fewer than two commas means no locator at all (previously, a bare `"Author, Title"` citation with no locator would have wrongly swallowed the title as the locator, which is corrected the same way). See `tests/unit/test_citation_resolution.py`.

**Implemented (T10/T11).** `symbol_schema.py` has no `RelationshipFile` type — correspondences are always inline on an `InterpretationEntry` (FR19), matching the format above. `symbol_loader.load_directory(root, store)` recursively discovers `traditions/`, `sources/`, `symbols/` anywhere under `root` (so one call can span several domain directories, e.g. `tests/fixtures/` containing both `tarot/` and `kabbalah/`), fully resolving every name reference (FR18) via a tiered matcher — exact slug, then exact case-insensitive name, then a word-subset match where every significant word in the query must appear in the candidate's name — before writing anything (FR5). The word-subset tier is what resolves an informal reference like `according_to: "Golden Dawn"` against a tradition named "Golden Dawn Kabbalah" without requiring curators to type the tradition's full name or slug verbatim. `cites` (a free-text string, e.g. `"Waite, Pictorial Key to the Tarot, p. 97"`) is split on its last comma — the trailing segment is the locator, the rest is resolved as a source query through the same tiered matcher (word-subset against title+author combined, since an informal citation rarely repeats a source's `title` field verbatim). See `tests/unit/test_symbol_schema.py` and `tests/unit/test_symbol_loader.py`.

**Revised again after further review (this pass): `RELATES_TO` moved from `Interpretation -> Interpretation` to `Symbol -> Symbol`.** The trigger was FR22: a symbol with zero interpretations (e.g. a bare Tree of Life path referenced only as someone else's correspondence target) couldn't previously be a `RELATES_TO` endpoint at all, since there was no `Interpretation` node for the edge to attach to. Since `according_to_tradition_id` already carries the claim's full attribution, scoping the edge to a *specific* interpretation of each endpoint was redundant — removing that requirement fixes the gap and simplifies name resolution (a `corresponds_to` target is just a symbol, not a symbol-plus-which-interpretation-of-it). `RelationshipFact.target_interpretation_id`/`target_tradition` were dropped from `core/models.py`; `Symbol` gained a `relationships` field (`Interpretation` lost the one it had) — see `core/graph/schema.py`, `core/graph/store.py`, `core/models.py`, and `tests/unit/test_graph_store.py::test_relationship_target_with_zero_interpretations_is_valid`.

## Chroma vector store design

Single `mythrix_sources` collection (not per-tradition) — simpler, and keeps a future cross-tradition query from requiring fan-out across collections. `tradition_slug`/`domain` are metadata filters instead.

Chunking: structure-aware first pass (split on section/paragraph breaks), recursive character splitter as fallback, target ~500–800 tokens with ~100 token overlap — tunable and independently tested, since naive fixed-size chunking risks severing a claim from its supporting context in list-like correspondence text (e.g. "Element: Fire").

Chunk metadata: `source_id` (links back to the Kùzu `Source`), `source_title`, `source_author`, `tradition_slug`, `domain`, `symbol_tags` (best-effort, informational only in v1), `chunk_index`/`char_start`/`char_end`, `ingested_at`, `embedding_model`.

Retrieval (FR7, FR8): `RetrievalPipeline.retrieve(graph_facts)` searches the **full** Chroma corpus by default — no `tradition_slug` filter — and the similarity-search query text is constructed from the graph facts (canonical name, attribute values, summary) — never from raw CLI free text. The embedding model must match between ingestion and query time; it's recorded in chunk metadata so a mismatch can be detected and reported rather than silently degrading similarity scores.

**Revised from the original design (which scoped every query to just the queried symbol's own tradition): an uploaded document is meant to be read *through* an established symbol's meaning, not treated as if it must belong to that symbol's tradition to be relevant** — e.g. a query for "The Tower" (tradition `rider-waite`) should be able to surface a passage from the Bible (tradition `douay-rheims`, domain `scripture`) about the Tower of Babel, since the whole point is discovering where established symbolism resonates in a text that was never authored as an interpretation of it. `ChromaVectorStore.similarity_search`'s `tradition_slug` parameter still exists (unchanged) for a future, narrower "just this tradition's own sources" scoping need — `RetrievalPipeline` simply doesn't pass it by default anymore. See the Risks entry below on what this does *not* yet solve.

**Idempotent/updatable ingestion via content hash (FR23).** `document_loader.py` computes a SHA-256 hash of the raw file bytes before chunking. It then compares that hash against the `content_hash` already recorded on the `Source` node (via `KuzuGraphStore.get_source`):

- **Unseen** (`Source.content_hash` is empty — never ingested): chunk, embed, add to Chroma, then set `content_hash`/`ingested_at` on the `Source`.
- **Unchanged** (hash matches): no-op — skip chunking/embedding/writing entirely. This is what makes re-running `load-documents` on the same file safe (FR23), distinct from `symbol_loader`'s idempotency, which relies on Kùzu `MERGE` rather than a hash comparison, since a text blob has no natural upsert key of its own.
- **Changed** (hash differs — the file was edited): delete this source's existing chunks from Chroma (`ChromaVectorStore.delete_by_source(source_id)`, T13) before adding the newly chunked/embedded content, then update `content_hash`/`ingested_at`. This is what "replaces rather than accumulates stale chunks" means in FR23 — without it, an edited source would leave superseded paragraphs retrievable alongside the corrected ones, silently corrupting citations.

`content_hash` lives only on `Source` in Kùzu (the authoritative record of what's currently ingested for that source) — it is not duplicated into each Chroma chunk's metadata, since `Source` is already the single source of truth and duplicating it would just be another place for the two stores to drift out of sync. This assumes one ingested document per `Source` (matches v1's reference-implementation scope of a single excerpt per source); citing several distinct documents under one bibliographic `Source` would need a separate per-document tracking entity instead of a single hash field, and is out of scope until it's actually needed.

**Implemented (T12–T14).** `core/embedding.py` holds a single shared `Embedder` Protocol (used by both the document loader and, below, the retrieval pipeline) rather than each defining its own, since both need the identical interface for a test to inject a fake. `ChromaVectorStore` explicitly configures the collection for **cosine distance** (`metadata={"hnsw:space": "cosine"}`) rather than Chroma's `l2` default — cosine gives `VectorHit.distance` a predictable `[0, 2]` range, which is what makes `1 - distance` a stable similarity score in `RetrievalPipeline` below; an unbounded, embedding-model-scale-dependent `l2` distance would not support that conversion. `KuzuGraphStore` gained a public `get_source(source_id)` (raising the new `SourceNotFoundError`) for the document loader's existence check and hash lookup.

**Implemented (T15).** `RetrievalPipeline.retrieve(graph_facts)` embeds `build_query_text(graph_facts)` (canonical name, tradition display name, summary, and each attribute as `"key: value"` — FR8) via the injected `Embedder`, calls `ChromaVectorStore.similarity_search` scoped to `graph_facts.interpretation.tradition.slug` (FR7), and hydrates each returned `VectorHit` into a full `RetrievedPassage` — joining `hit.source_id`/`hit.tradition_slug` against `KuzuGraphStore.get_source`/`get_tradition` (the latter newly made public, mirroring `get_source`) to attach the real `Source`/`Tradition` objects a citation needs (FR13). `RetrievedPassage.score` is `1 - hit.distance` (a cosine similarity, higher is better); `Settings.retrieval_min_score` filters passages by `score >= min_score`, matching the field's "keep at or above this" name. The pipeline itself never queries Kùzu directly — it only reads the `GraphFacts` already produced by `KuzuGraphStore.get_interpretation` plus the two small hydration lookups, keeping `RetrievalPipeline` a pure "already-retrieved graph facts in, retrieval context out" function per the domain-agnostic boundary in "Package layout".

## LangChain + Ollama synthesis

Config (`core/config.py`): `kuzu_db_path`, `chroma_persist_dir`, `ollama_base_url`, `embedding_model` (default `nomic-embed-text`), `generation_model` (no hardcoded default — fail with an actionable "run `ollama pull <model>`" error), `retrieval_top_k`, `retrieval_min_score`.

Retrieval (Kùzu + Chroma) stays plain deterministic Python; the LLM is never given tool-calling access to the graph or vector store (FR10, FR11) — it only receives the final assembled context: a `GRAPH FACTS` block (`[G1]`, `[G2]`, ...) built directly from `GraphFacts`, and a `PASSAGES` block (`[S1]`, `[S2]`, ...) built directly from retrieved chunks, each carrying its source/locator. System prompt instructs the model to state only what's in the supplied blocks, cite every substantive claim, say when information isn't present rather than inferring, and treat passage content as data to cite, not instructions to follow. `ChatOllama` runs at low temperature (~0.1–0.2).

A post-processing citation validator (`synthesis/citations.py`) scans output for `[G#]`/`[S#]` markers and rejects/flags any marker not present in the supplied context — this is what makes FR12 a code guarantee rather than a prompt request. `[G#]` markers are inherently trustworthy (sourced straight from Kùzu); `[S#]` markers prove the referenced id exists in context but not that the paraphrase is faithful to it (see Risks).

Per FR13, the References section rendered for every `[S#]` marker includes the full verbatim passage text alongside the source attribution and locator — not just an id/offset pointer — so a researcher can check the model's claim against the actual retrieved paragraph directly in the CLI output. This means `RetrievedPassage` (in `core/models.py`) must carry the chunk's full text through the entire pipeline (retrieval → synthesis input → output formatting), and `cli/formatting.py`'s human-readable and `--json` renderers both surface it (FR16).

**Implemented (T16–T18).** `synthesis/prompts.py` enumerates every *individual* graph fact — the symbol/interpretation identity as one line, then one line per `Interpretation.attribute` and one per `Symbol.relationship` — each getting its own `[G#]`, rather than one combined `[G1]` block for the whole `GraphFacts`. This is what lets the citation validator meaningfully distinguish "which specific fact was this claim grounded in" instead of every claim trivially citing a single catch-all marker. `graph_fact_ids`/`passage_ids` are exported from `prompts.py` and imported directly by `synthesis/citations.py`, so the set of "valid" markers a generated narrative is checked against can never drift from what was actually enumerated in the rendered prompt. `synthesis/chain.py`'s `OllamaSynthesizer` sets `validate_model_on_init=True` on `ChatOllama` so an unset or unreachable/unpulled model fails fast at construction (confirmed empirically: an unreachable `base_url` raises in ~15ms, not a long connection timeout) — both the unset-model and construction-failure paths are translated to `ModelUnavailableError`, and `synthesize()`'s own `invoke()` call is wrapped the same way, since the exact exception type an unavailable Ollama raises isn't asserted narrowly (varies across the `ollama`/`httpx` stack this proxies through). The real-Ollama path is covered by `tests/integration/test_synthesis_chain_ollama.py` (`@pytest.mark.requires_ollama`, not part of the default `tests/unit` run) rather than `tests/unit`, matching plan.md's package layout (`tests/integration/ # opt-in, requires a running Ollama`) — this wasn't run in the implementing session (no local Ollama available there); it needs a real run once per "Definition of done for v1."

## CLI design

Typer-based (type-hint-driven; stdlib `argparse` is a viable zero-dependency alternative if minimizing dependencies becomes a priority — left open for the tasks/implementation stage).

```
mythrix query --symbol <slug> --tradition <slug>
              [--include-related-traditions] [--top-k N]
              [--facts-only] [--json] [--strict]

mythrix load-symbols <path> [--dry-run] [--json]

mythrix load-documents <path> --tradition <slug>
              [--source-slug <slug>] [--chunk-size N] [--chunk-overlap N]
              [--dry-run] [--json]
```

- `query --facts-only` (FR14): dumps `GraphFacts` + retrieved passages without invoking Ollama.
- `query --strict` (FR15): turns a citation-validation failure into a non-zero exit instead of a soft warning.
- `query --json` (FR16): full evidentiary chain — fact ids, chunk ids/offsets, retrieved passage text, embedding/generation model identifiers, timestamp.
- `load-symbols`: validates all files (schema + referential integrity) before writing anything; `--dry-run` reports the planned diff without committing.
- `load-documents`: scoped to a single `--tradition` per invocation, matching the Chroma metadata design; requires the `Source` to already be registered via `load-symbols` so `source_id` can be validated against the graph.

**Implemented (T19–T22).** `--include-related-traditions` was **not** built — cross-tradition comparison synthesis is an explicit v1 non-goal in `spec.md`, and nothing else in scope needed it; it can be added later without disturbing anything here. Every command splits into a plain, dependency-injected function (`run_query`, `run_load_symbols`, `run_load_documents` — returning a process exit code, not raising `typer.Exit` itself) and a thin `@app.command()`-decorated wrapper that builds real `KuzuGraphStore`/`ChromaVectorStore`/`OllamaEmbedder`/`OllamaSynthesizer` instances from `Settings` and delegates. This is what let `tests/unit/test_cli_*.py` exercise real argument-parsing/exit-code/output behavior without a subprocess or a running Kùzu/Chroma/Ollama for most cases:
- `load-symbols --dry-run` calls `symbol_loader.build_plan()` directly (the same validation pass `load_directory` runs internally, just without the write phase) rather than a separate diff mechanism, so "nothing is written" is structural.
- `load-documents --dry-run` only hashes the file and compares it to the `Source.content_hash` already in Kùzu — it never constructs an embedder or vector store, so it works without a reachable Ollama daemon (`test_cli_load_documents.py` covers this offline). `--domain` was dropped from the flag set — the `Tradition.domain` is looked up from the graph instead of asking a curator to repeat it.
- `query`'s `--facts-only` path never constructs a `Synthesizer` at all (verified by a test whose fake `synthesizer_factory` raises if called), so it needs a reachable embedder (for the Chroma similarity search) but not a reachable generation model.
- `cli/formatting.py` reuses `synthesis/prompts.py`'s `render_graph_facts_block`/`render_passages_block` for the human-readable References section, so what a researcher reads is exactly what the model was shown, not a separately-maintained rendering.

## Risks and trade-offs

- **Kùzu maturity.** Pre-1.0, DDL has shifted release-to-release. Mitigation: pin an exact version, isolate all DDL in `graph/schema.py`, keep a canary integration test that creates the schema and round-trips a query on every dependency bump.
- ~~**Multi-edge support for alternative correspondence claims.**~~ **Resolved (T8).** The design relies on Kùzu allowing multiple `RELATES_TO` edges of the same type between the same node pair (e.g. two competing letter attributions for one card) without an implicit uniqueness constraint — confirmed against the pinned version in `tests/unit/test_kuzu_multi_edge_risk.py` (re-verified against `Symbol -> Symbol` endpoints after that change).
- **Kùzu concurrency.** Effectively single-writer, embedded — fine for CLI/loader usage; a future server/API mode would need revisiting (matches the non-goal on concurrent writes).
- **Chroma embedded-mode limitations.** `PersistentClient` isn't safe for concurrent multi-process writers — don't run `load-documents` and `query` concurrently against the same directory in v1.
- **Chunking strategy risk.** Needs empirical tuning against real source text rather than trusting default parameters, since naive splitting can weaken citation quality on correspondence-list-style text.
- **Prompt injection via retrieved documents.** Passage text is inserted directly into the synthesis prompt. Mitigated in v1 by data-not-instructions framing and citation-marker validation (catches fabricated ids); full adversarial hardening is out of scope (matches the non-goal), acceptable since v1 sources are curator-supplied.
- **Unscoped retrieval risks blending competing interpretive traditions once a second one exists.** Dropping the default `tradition_slug` filter (see "Chroma vector store design") is deliberate and correct for reading an independent document (Genesis, Sepher Yetzirah, ...) through an established symbol's meaning — but if a second *interpretive* tradition's own commentary is ever ingested for the same domain (e.g. Crowley's Thoth-deck writing, alongside Waite's), an unscoped query could surface both traditions' passages side by side without distinguishing them, which is exactly the "meaning collapse" the `Interpretation` entity exists to prevent everywhere else in this design. No mechanism exists yet to tell "an independent corpus, safe to search unscoped" apart from "a second competing interpretive tradition, needs explicit scoping" — this is unaddressed, not silently solved, and must be resolved (e.g. a flag on `Tradition` distinguishing interpretive traditions from open corpora, or reviving the dropped `--include-related-traditions` CLI idea) before a second interpretive tradition's documents are added.
- **Citation-id correctness ≠ content faithfulness.** The validator proves a marker refers to real context, not that the paraphrase is accurate. A future entailment/faithfulness check (e.g. NLI model or second LLM pass) is natural v2 work, explicitly out of v1 scope.
- **Local model availability varies.** No hardcoded generation-model default; fail with an actionable error rather than an opaque connection error.
- ~~**Idempotent loading complexity.**~~ **Resolved (T9).** Kùzu's `MERGE ... ON CREATE SET ... ON MATCH SET ...` handles idempotent upserts natively against the pinned version — confirmed by `tests/unit/test_graph_store.py`'s `test_upserts_are_idempotent`. No custom exists-then-insert/update logic was required. Real test coverage here is still worth keeping as curators iterate on YAML, but the anticipated implementation complexity didn't materialize.
- ~~**Domain-agnosticism is a process risk.**~~ **Resolved (T23).** `tests/unit/test_domain_agnosticism.py` greps every `.py` file under `src/mythrix/core`/`src/mythrix/cli` — with docstrings (via `ast.get_docstring`) and `#`-comments stripped first — against a deny-list of domain terms, using word-boundary regex matching (so e.g. "card" doesn't false-positive on "discard"). Docstrings/comments are deliberately exempt: explaining *why* the schema is domain-agnostic legitimately requires naming example domains (this file's own module docstring does exactly that), so the guardrail only judges identifiers, string literals, and other actual code. It caught a real violation on first run — `cli/commands/query.py`'s `--help` text used `"rider-waite"`/`"the-tower"` as example values — fixed by rewording to a domain-neutral example. A `test_deny_list_actually_catches_a_planted_violation` test proves the mechanism itself works (plants a literal in a temp file and confirms detection), satisfying the task's "temporarily introduce a domain literal... to confirm the test catches it" verification without needing to hand-edit and revert real source each time.
- **Testing LLM-dependent code.** `ChatOllama`/`OllamaEmbeddings` need a running Ollama daemon unavailable in CI by default. Mitigation: `Embedder`/`Synthesizer` abstractions (Protocol-based) so unit tests inject fakes; real-Ollama tests behind an opt-in `@pytest.mark.requires_ollama` marker.

## Traceability

Every FR in `spec.md` maps to a concrete decision above: FR1–FR3 → Kùzu schema; FR4–FR5 → structured-data loader; FR6–FR8 → Chroma design; FR9–FR13 → query/synthesis flow (including verbatim source-passage display); FR14–FR16 → CLI; FR17 → domain-agnosticism guardrail; FR18–FR22 → structured-data authoring format (name-based references, inline correspondences, keywords, symbol-intrinsic properties, optional interpretations); FR23 → content-hash-based idempotent/updatable document ingestion.

## Next step

Per this repo's Spec-Driven Development process, implementation does not begin here. The next step is a `tasks.md` breaking this plan into ordered, independently verifiable steps (repo scaffolding/`pyproject.toml`, `core/graph`, `core/vector`, `core/synthesis`, `loaders`, `cli`, tests), to be written and checked off in a subsequent pass.
