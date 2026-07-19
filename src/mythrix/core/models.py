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


class RetrievalContext(MythrixModel):
    """Everything retrieved for a query: graph facts plus grounding document passages."""

    graph_facts: GraphFacts
    passages: tuple[RetrievedPassage, ...] = ()


class InterpretationResult(MythrixModel):
    """Final synthesized output: narrative text plus the full evidentiary chain (FR12, FR16)."""

    context: RetrievalContext
    narrative: str
    generation_model: str
    embedding_model: str
    citation_markers_valid: bool
    invalid_markers: tuple[str, ...] = ()
    generated_at: datetime
