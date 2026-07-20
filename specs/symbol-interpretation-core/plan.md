# Symbol Interpretation Core — Plan

Technical approach for the requirements in `spec.md`.

## Package layout

```
pyproject.toml
src/
  mythrix/
    core/                        # DOMAIN-AGNOSTIC. No tarot (or any domain) literals allowed here.
      models.py                  # Sign, Tradition, Manifestation, Property, Interpretant,
                                  # QueryDirective, IntersemioticInterpretant, Source, Citation,
                                  # GraphFacts, RetrievedPassage, ConceptCandidates,
                                  # ConceptMatchScore, ConceptPairCandidates, MergedCandidate,
                                  # RetrievalContext, SignSummary
      config.py                  # kuzu_db_path, chroma_dir, ollama_base_url,
                                  # embedding_model, generation_model, retrieval_top_k, ...
      errors.py                  # SignNotFoundError, TraditionNotFoundError,
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
        sign_schema.py              # pydantic models mirroring the YAML authoring format
        sign_loader.py               # validates + idempotently upserts YAML into KuzuGraphStore
        document_loader.py           # reads source docs, chunks, embeds, upserts into Chroma
    cli/
      main.py                      # `mythrix` entrypoint (Typer), registers subcommands
      commands/
        query.py
        load_symbols.py
        load_documents.py
      formatting.py                # shared human-readable + --json renderers
data/
  semiotic_systems/                # reference datasets — content only, never imported by mythrix.core
    tarot/
      traditions/rider-waite.yaml
      sources/waite-pictorial-key.yaml
      signs/the-fool.yaml           # intersemiotic interpretants declared inline (FR19)
    hebrew_alef_bet/
      traditions/golden-dawn-kabbalah.yaml
      signs/samekh.yaml             # intrinsic properties (FR21) + its own tradition-scoped manifestation
  corpus/                          # RAG document corpus — no Tradition (FR6, FR7)
    scripture/
      en_drb/
        douay-rheims-bible.yaml     # source metadata, colocated with its raw text
        douay-rheims-bible.txt
tests/
  unit/
  integration/                    # opt-in, requires a running Ollama
  fixtures/semiotic_systems/{tarot,hebrew_alef_bet}/
```

`src/mythrix/core/**` and `src/mythrix/cli/**` contain no tarot/Kabbalah/etc. literal — no `Suit` enum, no `arcana_number` field. All domain content lives in `data/**` or `tests/fixtures/**`. Enforced by `tests/unit/test_domain_agnosticism.py`, which greps `core/`/`cli/` for a deny-list of domain terms (FR17).

CLI/API surface vocabulary (`mythrix query --symbol/--tradition`, `/api/symbols`, `/api/traditions`, `SignSummary`'s exposed field names) keeps the word "symbol" where it already appears in user-facing flags and endpoint paths — the Peircean rename below applies to the domain model and its authoring format, not to the CLI/API vocabulary.

`RetrievalPipeline.retrieve()` and the synthesis chain take already-structured `GraphFacts`/`RetrievalContext` objects, not raw CLI argv or free text — a future conversational-agent layer produces those structured inputs without touching retrieval/synthesis internals.

## Domain model (`core/models.py`)

```python
class Tradition(MythrixModel):
    id: str
    slug: str
    name: str
    domain: str
    description: str = ""

class Source(MythrixModel):
    id: str                        # always authored explicitly, never derived from a filename
    domain: str                    # e.g. "tarot", "scripture" — same vocabulary as Tradition.domain
    citation_label: str = ""       # attributes a retrieved passage (FR13); empty for a citation-only source
    title: str
    author: str
    publication_year: int | None = None
    license: str = ""
    uri: str = ""
    description: str = ""
    content_hash: str = ""
    ingested_at: datetime | None = None

class Citation(MythrixModel):
    source: Source
    locator: str = ""

class Property(MythrixModel):
    """A static, structural fact — never used to build retrieval query text (FR8, FR21),
    at either the Sign or Manifestation scope it may attach to."""
    id: str
    key: str
    value: str
    position: int = 0

class QueryDirective(MythrixModel):
    """A curator-authored retrieval instruction on one Interpretant (FR8, FR28).
    `directive` is free text; v1 code interprets only `"filter"`."""
    directive: str
    as_token: str

class Interpretant(MythrixModel):
    """A conceptual token evoked by a sign within one manifestation — always
    eligible for retrieval query construction (FR8, FR24) unless it carries a
    `query.directive: "filter"` annotation, in which case it is applied as a
    literal-text filter instead of a plain query (FR28)."""
    id: str
    type: str = "concept"
    value: str
    position: int = 0
    query: QueryDirective | None = None

class Sign(MythrixModel):
    """A domain-agnostic sign anchor. `canonical_name` is an internal/fallback
    label; the tradition-specific display name shown to users lives on
    `Manifestation.display_name` (FR2)."""
    id: str
    slug: str
    canonical_name: str
    sign_type: str
    semiotic_system: str
    notes: str = ""
    properties: tuple[Property, ...] = ()
    intersemiotic_interpretants: tuple[IntersemioticInterpretant, ...] = ()

class IntersemioticInterpretant(MythrixModel):
    """A typed, attributable claim from one sign to another (FR3, FR19).
    `according_to` records the tradition/attribution-system asserting this
    specific claim. `target_interpretants` is the target sign's own
    manifestation-level interpretants, gathered across every tradition it is
    manifested under, for retrieval query construction (FR8) — it never
    includes `target_sign.properties` or any manifestation's `properties`."""
    relationship: str
    target_sign: Sign
    according_to: Tradition
    description: str = ""
    symmetric: bool = False
    confidence: str = "attributed"
    target_interpretants: tuple[Interpretant, ...] = ()
    citation: Citation | None = None

class Manifestation(MythrixModel):
    """A sign as understood within one tradition — the join entity that keeps
    distinct traditions' meanings from collapsing into one."""
    id: str
    sign_id: str
    tradition: Tradition
    display_name: str
    denotation: str = ""
    properties: tuple[Property, ...] = ()
    interpretants: tuple[Interpretant, ...] = ()
    citations: tuple[Citation, ...] = ()
    created_at: datetime

class SignSummary(MythrixModel):
    slug: str
    canonical_name: str
    sign_type: str
    tradition_slugs: tuple[str, ...] = ()

class GraphFacts(MythrixModel):
    sign: Sign
    manifestation: Manifestation
```

`ConceptCandidates`, `ConceptMatchScore`, `MergedCandidate`, `ConceptPairCandidates`, `RetrievalContext`, `RetrievedPassage` keep their existing class and field names — they describe retrieval-algorithm output, not the authoring vocabulary — except `RetrievalContext.graph_facts.sign`/`.manifestation` replacing `.symbol`/`.interpretation`, and `RetrievedPassage` carrying no `tradition` field at all: a retrieved passage always comes from an independent corpus document (FR7), which has no interpretive tradition of its own; `source.citation_label` attributes it instead.

## Kùzu graph schema (`core/graph/schema.py`)

```
CREATE NODE TABLE Sign(id, slug, canonical_name, sign_type, semiotic_system, notes, PRIMARY KEY(id))
CREATE NODE TABLE Tradition(id, slug, name, domain, description, PRIMARY KEY(id))
CREATE NODE TABLE Manifestation(id, sign_id, tradition_id, display_name, denotation, created_at, PRIMARY KEY(id))
CREATE NODE TABLE Property(id, key, value, position, PRIMARY KEY(id))
CREATE NODE TABLE Interpretant(id, type, value, position, query_directive, query_as_token, PRIMARY KEY(id))
CREATE NODE TABLE Source(id, domain, citation_label, title, author, publication_year, license, uri, description, content_hash, ingested_at, PRIMARY KEY(id))

CREATE REL TABLE HAS_MANIFESTATION(FROM Sign TO Manifestation)
CREATE REL TABLE MANIFESTED_IN(FROM Manifestation TO Tradition)
CREATE REL TABLE HAS_PROPERTY(FROM Sign TO Property, FROM Manifestation TO Property)
CREATE REL TABLE HAS_INTERPRETANT(FROM Manifestation TO Interpretant)
CREATE REL TABLE CITES(FROM Manifestation TO Source, locator STRING)
CREATE REL TABLE INTERSEMIOTIC(
    FROM Sign TO Sign,
    relationship STRING,
    description STRING,
    symmetric BOOLEAN,
    confidence STRING,
    according_to_id STRING,
    source_id STRING
)
```

`Property` and `Interpretant` are separate node tables. `HAS_PROPERTY` is the one remaining multi-FROM-pair rel table (`Sign -> Property` for intrinsic facts, `Manifestation -> Property` for tradition-scoped structural facts), disambiguated by node type in a single query pattern. `INTERSEMIOTIC` connects `Sign -> Sign` directly, not `Manifestation -> Manifestation`: `according_to_id` carries the claim's attribution independently of which tradition either endpoint's own manifestation belongs to, and a sign with zero manifestations is still a valid endpoint (FR22). Kùzu permits multiple edges of the same rel table between the same node pair, so alternative/competing claims for the same sign coexist as separate `INTERSEMIOTIC` edges rather than overwriting each other (`tests/unit/test_kuzu_multi_edge_risk.py`, re-targeted at `HAS_PROPERTY` and `INTERSEMIOTIC`).

Retrieval is always parametrized Cypher executed from plain Python (FR10): `KuzuGraphStore.get_manifestation()` composes several small, focused parametrized queries (sign lookup, tradition lookup, the manifestation itself, then properties/interpretants/citations/intersemiotic-interpretants each via their own query), never string-formatting user-facing values into query text.

## Graph store (`core/graph/store.py`)

Public surface: `upsert_tradition`, `upsert_source`, `upsert_sign` (writes the `Sign` node and its own `properties`), `upsert_sign_with_manifestation` (writes the `Sign`, the `Manifestation`, its `properties`, its `interpretants`, and its `citations`), `upsert_intersemiotic_interpretant`, `reconcile_sign_manifestations` (deletes a sign's stale manifestations — and their properties/interpretants — against a caller-supplied current set, since a manifestation's id is derived from its sign and tradition slugs and a tradition rename changes it), `get_manifestation`, `get_tradition`, `get_source`, `list_traditions`, `list_signs` (returns `SignSummary`, one row per sign with at least one manifestation).

Internal lookups: `_get_sign_by_slug`/`_get_sign_by_id` (shallow — a fetched sign's own `intersemiotic_interpretants` is `()` unless it is the top-level queried sign, to bound recursion through `IntersemioticInterpretant.target_sign`), `_get_sign_properties`, `_get_manifestation_properties`, `_get_interpretants`, `_get_all_manifestation_interpretants` (every interpretant across all of a sign's manifestations regardless of tradition — populates `IntersemioticInterpretant.target_interpretants` only, never properties), `_get_citations`, `_get_sign_intersemiotic_interpretants`.

## Authoring YAML format (`core/loaders/sign_schema.py`, `sign_loader.py`)

```python
class SignBlock(LoaderModel):
    id: str | None = None      # accepted for compatibility with docs/newmodel.yaml's worked
                                # example; never read by the loader — see "Sign identity" below.
    name: str
    type: str
    notes: str = ""
    properties: tuple[PropertyEntry, ...] = ()
    manifestations: tuple[ManifestationEntry, ...] = ()

class PropertyEntry(LoaderModel):
    key: str
    value: str

class QueryDirectiveEntry(LoaderModel):
    directive: str
    as_token: str

class InterpretantEntry(LoaderModel):
    type: str = "concept"
    value: str
    query: QueryDirectiveEntry | None = None

class IntersemioticInterpretantEntry(LoaderModel):
    target_system: str
    target_sign: str
    relationship: str
    according_to: str
    description: str = ""
    symmetric: bool = False
    confidence: str = "attributed"

class ManifestationEntry(LoaderModel):
    tradition: str
    display_name: str
    denotation: str = ""
    cites: tuple[str, ...] = ()
    properties: tuple[PropertyEntry, ...] = ()
    interpretants: tuple[InterpretantEntry, ...] = ()
    intersemiotic_interpretants: tuple[IntersemioticInterpretantEntry, ...] = ()

class SignFile(LoaderModel):
    semiotic_system: str
    sign: SignBlock

class SourceBlock(LoaderModel):
    id: str                        # always authored — a corpus source's file is named
                                    # descriptively, not with its reference key (see below)
    domain: str
    citation_label: str = ""
    title: str
    author: str
    publication_year: int | None = None
    license: str = ""
    uri: str = ""
    description: str = ""

class SourceFile(LoaderModel):
    source: SourceBlock
```

`manifestations` lives on `SignBlock`, nested under `sign:` in the YAML, not as a top-level sibling key — a sign's manifestations are part of describing that sign, not a separate section of the file.

**Sign identity.** `Sign.id`/`.slug` are the YAML file's stem, exactly as `Symbol.id` was before this rewrite. `SignBlock.id` is parsed but not read by `build_plan()` — it exists only so a file copying `docs/newmodel.yaml`'s worked example verbatim does not fail shape validation under `extra="forbid"`.

**Source identity (asymmetric with Sign identity).** `SourceBlock.id` is always authored explicitly and is what `_load_sources()` reads — unlike a sign, a source's own filename is never the identity key. A citation source's file is still conventionally named after its id (`waite-pictorial-key.yaml`, `id: "waite-pictorial-key"`), but a corpus source's file is named descriptively (`douay-rheims-bible.yaml`) while its id is a short reference key (`id: "en_drb"`) — the two need not match, since a source is never referenced by curators repeating its slug across other files (a manifestation's `cites:` resolves by fuzzy title/author match; a corpus source's directory-mate `.txt` is found by filename stem, not by id).

**No `value_type` field.** `Property`/`Interpretant` (and their authoring-format counterparts) carry no `value_type` — nothing in the codebase ever reads it; an interpretant's eligibility for exact-value filtering is decided entirely by whether it carries a `query` directive (FR8, FR28), not by a separate type-hint field. Retained through the first version of this rewrite as a carryover from the retired `Attribute.value_type`, then removed once confirmed dead.

**Bare-number values.** `PropertyEntry`/`InterpretantEntry`'s `value` field_validator accepts a YAML list (comma-joining it, as before) or a bare `int`/`float` (stringified) in addition to a plain string — `value: 9` and `value: "9"` normalize to the same internal `"9"`. `bool` is excluded from the numeric coercion despite being an `int` subclass in Python, so an unquoted `yes`/`no`/`true`/`false` (a well-known YAML footgun) still fails validation rather than silently becoming the string `"True"`/`"False"`.

**Intersemiotic-interpretant resolution.** `target_system` is required on every `intersemiotic_interpretants` entry. `build_plan()` filters the full parsed-sign pool to `semiotic_system == entry.target_system` before resolving `target_sign` against it, using the existing tiered resolution (exact slug, then exact case-insensitive name, then a forgiving word-subset match). An `entry.target_system` matching no parsed sign raises a distinct `IngestValidationError` ("no sign found in semiotic system %r") ahead of the name-resolution tiers. `according_to` (a tradition reference) resolves against the full, unscoped tradition pool.

**Interpretants replace attributes and keywords.** `ManifestationEntry.interpretants` is the single list for what was previously split across `attributes:` and `keywords:` — a keyword becomes an `interpretants` entry with `type: "concept"`. `PropertyEntry`/`InterpretantEntry` retain the existing `value`-list-join `field_validator` (comma-joining an authored YAML list at parse time; `retrieval.pipeline._atomic_values` splits it back into one query per concept at query-build time).

Two-pass loading (`build_plan()` then `_write_plan()`) is unchanged in structure: pass 1 parses and resolves every reference in memory, raising `IngestValidationError` with nothing written on any unresolved/ambiguous reference or duplicate slug; pass 2 writes only if pass 1 raised nothing (FR4, FR5).

## Retrieval pipeline (`core/retrieval/pipeline.py`)

Similarity-search query text is built entirely from already-retrieved `GraphFacts` — an `Interpretant.value`, never from `Sign.properties`/`Manifestation.properties`, never from `Sign.canonical_name`/`Manifestation.display_name`/`Manifestation.denotation`, and never from raw user input (FR8). One query per individual atomic concept: one per `_atomic_values`-split value in each of the manifestation's own `interpretants`, then for every `intersemiotic_interpretants` entry (FR3, FR19), one per atomic concept in `target_interpretants` — the target sign's own `properties` are excluded from this at every call site, including inside an intersemiotic-interpretant's target, which is the one behavior change relative to the prior implementation (previously a relationship target's `properties` were folded in via `target.properties + relationship.target_semantic_facts`; they are not folded in here).

An interpretant carrying `query.directive == "filter"` is excluded from the plain-concept list and instead contributes a `_FilterToken(value=interpretant.value, as_token=interpretant.query.as_token)`. Every recognized filter token anywhere in the current `GraphFacts` — the manifestation's own interpretants and every intersemiotic target's `target_interpretants` — is collected once (`_collect_filter_tokens`), deduplicated by `as_token`, and applied as an *additional* `document_contains` literal-text filter query to every plain concept query, regardless of which group produced the token; the plain query for every concept is always issued as well, so a filter token never causes a concept's ordinary result set to be replaced or suppressed.

Concept-scoped retrieval (FR24): every `_Query` sharing the same `Interpretant.value` shares that value as its grouping key (`concept`); hits within a concept are combined by Reciprocal Rank Fusion (`_RRF_K = 60`) across only that concept's own queries, searched to `match_pool_size` depth and displayed to `top_k`.

Concept-pair convergence (FR27, FR28): every unordered pair of concepts sharing a chunk in their deep pools, plus every concept paired with every recognized filter token sharing a chunk, is grouped into a `ConceptPairCandidates`, scored by the geometric mean of the pair's semantic component scores (clamped at zero) for two semantic concepts, or by the semantic concept's own score alone for a concept-plus-filter-token pair (the filter token contributes membership, not a score, since its membership is a guarantee of literal containment rather than a similarity judgment).

Concept-pair identity (FR27) is keyed by `Interpretant.value` text alone; `Interpretant.type` is descriptive/display metadata and does not participate in concept grouping.

## Document corpus (`core/vector/store.py`, `core/loaders/document_loader.py`)

`ChunkMetadata`/`VectorHit` carry `source_id` and `domain` only — no `tradition_slug`. `ChromaVectorStore.similarity_search` takes no tradition parameter; every call searches the full corpus (FR7), matching what was already true in practice (no chunk has ever carried a tradition that mattered for scoping).

`data/corpus/<domain>/<source-id>/` colocates a corpus source's structured-data YAML with the raw text it describes, both sharing a filename stem (e.g. `douay-rheims-bible.yaml` + `douay-rheims-bible.txt`) — the directory name (`en_drb`) is conventionally the source's `id`, though nothing enforces that; the id comes from the YAML's own `source.id` field, not the path.

`document_loader.load_document()` no longer takes `tradition_slug`/`domain` parameters — a chunk's `domain` comes from the already-declared `Source.domain`, fetched the same call already makes to check `content_hash` (FR23).

`document_loader.load_corpus_directory(root, ...)` auto-discovers every `<name>.yaml`/`<name>.txt` pair under `root`: parses each YAML as a `SourceFile`, registers the `Source` (refreshing its metadata on every pass while preserving `content_hash`/`ingested_at` from whatever's already stored, so re-running doesn't defeat FR23's idempotency), then calls `load_document()` on the colocated text. Every pair is parsed before any of them is registered or ingested, so a duplicate `id` across corpus files is caught before anything is written — mirrors `sign_loader.py`'s two-phase discipline. `dry_run=True` only hashes each `.txt` and compares it to the existing `Source.content_hash`, if any; nothing is written, `vector_store`/`embedder` may be `None`.

`mythrix load-documents` takes a directory root (no `--tradition`/`--domain`/`--source-slug`) and calls `load_corpus_directory` directly.

## Data migration

`data/**/*.yaml`, `data/**/*.txt`, and `tests/fixtures/**/*.yaml` are rewritten from the prior format and layout to the current one by one-off scripts (deleted after use, never a permanent dual-format loader):

1. `symbol:` → `sign:`, nested under a new required top-level `semiotic_system:`; `interpretations:` → `manifestations:`, nested under `sign:` rather than left as a top-level sibling key; `summary:` → `denotation:`.
2. Every prior `retrievable: false` property/attribute becomes a `properties:` entry at the scope it already occupied (sign-level property stays sign-level; interpretation-level attribute becomes that manifestation's own `properties:` entry), with the flag dropped. Every prior `retrievable: true`/default sign-level property moves into that sign's manifestation's `interpretants:`; a `value_type: integer` one additionally gains `query: {directive: filter, as_token: <word>}`, computed once via an English-number-word table as a migration-time utility (not carried into runtime code). Every prior `retrievable: true`/default interpretation-level attribute becomes an `interpretants:` entry (`key` → `type`). Every `keywords:` entry becomes an `interpretants:` entry with `type: "concept"`. Every remaining `value_type:` entry is dropped, since nothing reads it.
3. `corresponds_to:` → `intersemiotic_interpretants:` (`to` → `target_sign`), with `target_system` filled from a name → `semiotic_system` map built from the same file set being migrated.
4. `data/tarot/` → `data/semiotic_systems/tarot/`, `data/kabbalah/` → `data/semiotic_systems/hebrew_alef_bet/` — each migrated sign's `semiotic_system:` value matches its new directory name exactly (`tarot`, `hebrew_alef_bet`). `data/bible/sources/*.yaml` + `data/bible/documents/*.txt` merge into `data/corpus/scripture/en_drb/douay-rheims-bible.{yaml,txt}`, gaining `id: "en_drb"`, `domain: scripture`, `citation_label: "Douay-Rheims"`, and a `description:`; `data/bible/traditions/douay-rheims.yaml` is deleted (FR6 — a corpus source has no `Tradition`). The three citation sources (`waite-pictorial-key`, `papus-tarot-bohemians`, `sepher-yetzirah`) gain an `id:` matching their filename stem and a `domain:` matching their sibling `Tradition.domain` (`tarot`/`kabbalah`).

Every migrated file is reviewed by hand before each script is deleted.

## Local database recreation

`.mythrix/graph.kuzu` (project-relative, per `Settings.kuzu_db_path`) is deleted and recreated against the new DDL — there is no schema-migration tooling, and `KuzuGraphStore._ensure_schema` only ever creates tables on an empty database. `.mythrix/chroma` (the vector store) needs no migration: Chroma's per-chunk metadata is a schemaless dict, so an already-ingested chunk's now-unread `tradition_slug` key is simply ignored, not read as `VectorHit` no longer has a field for it.

## Risks

- `query-viewer-web-ui` (`web/src/api/types.ts` and its consuming components) hardcodes the prior field names (`canonical_name`, `symbol_type`, `attributes`, `target_symbol`) sourced from `model_dump(mode="json")` on the classes renamed here. It is out of scope for this plan and is tracked as a follow-up against `specs/query-viewer-web-ui/`.
- Retrieval comparability across concepts and across pair-groups remains bounded by Reciprocal Rank Fusion and per-group geometric-mean scoring exactly as before this rewrite; this plan changes no scoring behavior, only what data feeds query-text construction.
