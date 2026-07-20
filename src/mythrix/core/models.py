"""Domain-agnostic core models shared across graph storage, retrieval, synthesis, and CLI output.

No domain-specific literals (tarot, Kabbalah, etc.) belong in this module — see
tests/unit/test_domain_agnosticism.py.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MythrixModel(BaseModel):
    """Base for all Mythrix domain models: immutable, strict, serializable.

    Frozen because these objects represent already-retrieved facts (the output of a
    graph query or a vector search) rather than entities being edited in place —
    mutating them in a later pipeline stage would silently break the evidence trail
    this project exists to keep auditable. Derive an updated value with
    ``model_copy(update={...})`` instead of assigning to a field.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class Tradition(MythrixModel):
    """An interpretive school/lens or attribution system (e.g. a specific deck tradition
    or a specific correspondence system)."""

    id: str
    slug: str
    name: str
    domain: str
    description: str = ""


class Source(MythrixModel):
    """A primary-source document citable by an interpretation or a relationship claim.

    `content_hash`/`ingested_at` are written by the document loader, not authored
    in a `Source` YAML file — they record what file (by content) is currently
    ingested for this source, so re-ingesting an unchanged file is a no-op and
    re-ingesting a changed one replaces its chunks rather than accumulating
    stale ones alongside the new content (FR23).
    """

    id: str
    title: str
    author: str
    publication_year: int | None = None
    license: str = ""
    uri: str = ""
    content_hash: str = ""
    ingested_at: datetime | None = None


class Symbol(MythrixModel):
    """A domain-agnostic symbol anchor.

    `canonical_name` is an internal/fallback label only — the tradition-specific display
    name actually shown to users lives on `Interpretation.display_name` (FR2).

    `properties` holds intrinsic, tradition-independent facts about the symbol itself
    (e.g. a Hebrew letter's alphabet position or numeric value) — true regardless of
    interpretive lens, unlike `Interpretation.attributes`, which holds tradition-scoped
    interpretive claims (e.g. element, keywords) that can genuinely differ by tradition.

    `relationships` holds this symbol's correspondences to other symbols (FR3, FR19).
    These live on `Symbol`, not `Interpretation`, because a correspondence claim is
    about the symbol itself, attributed to whichever tradition/system asserts it —
    not about one specific tradition's rendering of it — and because a symbol with no
    interpretation at all must still be able to participate in a correspondence.
    Relationship targets are shallow (their own `relationships` is always `()`) to
    avoid unbounded recursion; only the top-level queried symbol has this populated.
    """

    id: str
    slug: str
    canonical_name: str
    symbol_type: str
    notes: str = ""
    properties: tuple[Attribute, ...] = ()
    relationships: tuple[RelationshipFact, ...] = ()


class Attribute(MythrixModel):
    """A single key/value fact scoped to one interpretation (e.g. element -> Fire).

    `value_type` is a free-text hint for rendering (e.g. "string", "number", "list") —
    not an enforced enum, so new domains aren't blocked by a fixed type vocabulary a
    future curator hasn't anticipated. Unknown values should be treated as "string" by
    consumers rather than rejected.

    `retrievable` is the curator's own call on whether this fact should feed retrieval
    query construction (FR8) — default `True`. Some facts are purely identifying/
    bookkeeping (e.g. a tarot card's position number in its own deck) and would only
    inject a stray token into a similarity search; others that happen to share a
    superficial trait like "is a number" can still be real symbolic content (e.g. a
    Hebrew letter's gematria value) that must stay in. The distinction is a curatorial
    judgment about *this specific fact*, not something core/retrieval code can safely
    infer from the key name or value type alone — see plan.md's domain-agnosticism
    guardrail, which is exactly why that inference used to live in `core/retrieval/`
    and had to be pulled back out.
    """

    id: str
    key: str
    value: str
    value_type: str = "string"
    position: int = 0
    retrievable: bool = True


class Citation(MythrixModel):
    """A citation to a source, from either an interpretation or a relationship claim."""

    source: Source
    locator: str = ""


class RelationshipFact(MythrixModel):
    """A typed, attributable correspondence from one symbol to another (FR3, FR19).

    `according_to_tradition` records which tradition/attribution-system asserts this
    specific claim — deliberately the *only* attribution on the edge, since the claim
    is about the symbols themselves, not about a specific interpretation of either one.
    This is what lets multiple competing correspondence systems coexist without
    conflicting, and what lets a symbol with zero interpretations still participate.

    `confidence` is free text, not an enforced enum — e.g. "attributed", "traditional",
    "disputed", "speculative" are suggested starting points for curators, but this
    vocabulary is a documentation convention, not a validated closed set.

    `target_semantic_facts` is *not* part of the correspondence claim itself — it's
    the target symbol's own interpretation-level attributes, gathered across every
    tradition it's interpreted under, purely so retrieval query construction (FR8)
    can draw on what the target itself means, not just its bare `properties`. E.g. a
    tarot card's correspondence to a Hebrew letter should pull in that letter's own
    `foundation`/planetary or zodiacal assignment, not just intrinsic facts like its
    numeric value.
    """

    relationship_type: str
    target_symbol: Symbol
    according_to_tradition: Tradition
    description: str = ""
    symmetric: bool = False
    confidence: str = "attributed"
    target_semantic_facts: tuple[Attribute, ...] = ()
    citation: Citation | None = None


class Interpretation(MythrixModel):
    """A symbol as understood within one tradition — the join entity that keeps
    distinct traditions' meanings from collapsing into one. Correspondences to other
    symbols live on `Symbol.relationships`, not here — see `RelationshipFact`."""

    id: str
    symbol_id: str
    tradition: Tradition
    display_name: str
    summary: str
    attributes: tuple[Attribute, ...] = ()
    citations: tuple[Citation, ...] = ()
    created_at: datetime


class SymbolSummary(MythrixModel):
    """A lightweight listing of one symbol, for a picker to choose a
    symbol/tradition pair guaranteed to have an interpretation (FR9 of
    `specs/query-viewer-web-ui/spec.md`) — not a full `Symbol` (no
    `properties`/`relationships`), since a picker has no use for either."""

    slug: str
    canonical_name: str
    symbol_type: str
    tradition_slugs: tuple[str, ...] = ()


class GraphFacts(MythrixModel):
    """Deterministic result of a single graph query: one symbol, resolved for one
    tradition (v1 query scope, FR9)."""

    symbol: Symbol
    interpretation: Interpretation


class RetrievedPassage(MythrixModel):
    """A single retrieved document chunk, carrying full verbatim text for display (FR13)."""

    chunk_id: str
    source: Source
    tradition: Tradition
    text: str
    locator: str = ""
    score: float = 0.0
    chunk_index: int = 0
    char_start: int = 0
    char_end: int = 0
    embedding_model: str = ""


class ConceptCandidates(MythrixModel):
    """Retrieved passages for one individually-queried concept (FR24) — an attribute
    value, a keyword, or a relationship-target fact, exactly as decomposed by
    `retrieval.pipeline.build_query_texts`. Kept separate from every other concept's
    candidates rather than merged into one shared pool, so a well-supported concept
    (e.g. a precise numeric-fact match) can't be crowded out of the final output by
    unrelated concepts that simply generated more queries — the empirical failure
    this restructuring exists to fix (see plan.md's "Concept-scoped retrieval and
    synthesis"). Where two concepts both retrieve the same passage, that convergence
    is surfaced separately as `ConceptPairCandidates` (FR27).

    `concept` doubles as both the grouping key and the human-readable label shown in
    output — it's the atomic query text itself (e.g. "white horse", "laughter"),
    which is already exactly what a researcher would recognize the concept by.
    """

    concept: str
    passages: tuple[RetrievedPassage, ...] = ()


class ConceptMatchScore(MythrixModel):
    """One concept's own claim on a passage, within a pair match (FR27, FR28).

    `score` is that concept's best similarity for this passage. `exact_value` marks
    the FR28 case: a numeric fact (a gematria value, a deck position) reaches a
    passage through a literal-text filter, not through embedding similarity, so its
    membership is a *guarantee* that the passage contains that value rather than a
    similarity judgment. Such a match carries no meaningful magnitude — its `score`
    is not comparable to a semantic concept's and is excluded from the combined
    score (see `ConceptPairCandidates`).
    """

    concept: str
    score: float = 0.0
    exact_value: bool = False


class MergedCandidate(MythrixModel):
    """A passage two concepts both retrieved, with the components of its combined
    score kept alongside the verdict (FR27) — a researcher sees not just that a
    passage converged but how strongly it did on each side, which is what
    distinguishes a genuine intersection from a strong match on one concept that
    merely grazed the other."""

    passage: RetrievedPassage
    matches: tuple[ConceptMatchScore, ...] = ()
    combined_score: float = 0.0


class ConceptPairCandidates(MythrixModel):
    """Passages retrieved by *both* of two concepts (FR27) — emitted alongside, never
    instead of, each concept's own `ConceptCandidates`. Convergence is the signal
    per-concept grouping alone discards: a passage matching two independently-derived
    concepts at once is a stronger finding than either concept's own top hit, but
    under FR24 it is merely duplicated into two groups with nothing recording that
    it was the same passage.

    Because groups are additive, a strong single-concept match never loses to a
    convergent one — it still stands in its own concept's group — so no ranking rule
    has to adjudicate between the two kinds of result.

    Candidates are ranked by the geometric mean of the pair's *semantic* component
    scores, clamped at zero. Geometric rather than arithmetic because convergence is
    conjunctive: a passage scoring (0.90, 0.20) and one scoring (0.57, 0.53) have
    identical sums and means, but only the second genuinely sits at the intersection
    — the first is a strong match on one concept that merely reached the other's
    matching pool. Clamped because `1 - cosine_distance` spans [-1, 1], so a
    negative component would otherwise make the square root complex; a passage
    anti-correlated with one member has no conjunctive strength anyway. An
    `exact_value` member (FR28) contributes membership but no score, so a
    concept-plus-number pair is scored by its semantic concept alone.

    Scores are only comparable *within* a group, where every candidate is scored by
    the same two queries and any per-query bias is constant across the rows being
    compared. They are not comparable across groups — see plan.md's Risks.
    """

    concepts: tuple[str, ...] = ()
    candidates: tuple[MergedCandidate, ...] = ()


class RetrievalContext(MythrixModel):
    """Everything retrieved for a query: graph facts, grounding document passages
    grouped per concept (FR24), and the concept pairs those passages converge on
    (FR27). No synthesized text — the query path invokes no generation model (FR29)."""

    graph_facts: GraphFacts
    concept_candidates: tuple[ConceptCandidates, ...] = ()
    pair_candidates: tuple[ConceptPairCandidates, ...] = ()

    @property
    def all_passages(self) -> tuple[RetrievedPassage, ...]:
        """Every retrieved passage across every concept, flattened — for callers that
        only need a corpus-wide view (e.g. counting total passages retrieved), not
        the per-concept grouping itself. Deliberately excludes `pair_candidates`,
        which are *mostly* but not entirely a subset of these: pair membership is
        detected against a matching pool deeper than the one displayed here (FR27),
        so a passage can converge on two concepts while ranking below both of their
        displayed cutoffs. Callers needing every passage the query touched must read
        `pair_candidates` too."""
        return tuple(passage for candidates in self.concept_candidates for passage in candidates.passages)
