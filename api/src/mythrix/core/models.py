"""Domain-agnostic core models shared across graph storage, retrieval, and the API.

No domain-specific literals (tarot, Kabbalah, etc.) belong in this module — see
tests/unit/test_domain_agnosticism.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

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
    """A primary-source document citable by a manifestation or an intersemiotic
    interpretant, or ingested as an independent corpus document (FR-CO-01).

    `id` is always authored explicitly in the source's own YAML — unlike a
    `Sign`, a source is never referenced by curators repeating its slug across
    other files (a manifestation's `cites:` resolves by fuzzy title/author
    match, not by id), so an authored id carries none of the repetition risk
    FR-SD-03 exists to avoid for signs.

    `domain` names the broad subject area this source belongs to (e.g.
    "tarot", "scripture") — the same free-text vocabulary `Tradition.domain`
    already uses, not a `Sign.semiotic_system` value; a corpus source has no
    semiotic system of its own to belong to.

    `citation_label` is the short human-readable label used to attribute a
    retrieved passage in output (FR-RT-05) — e.g. "Douay-Rheims" — in place of
    `title`/`author`, which stay as full bibliographic metadata. Left empty
    for a source that is only ever cited via a `Citation` (never ingested
    into the vector store), since those render their own attribution from
    `title`/`author` directly.

    `content_hash`/`ingested_at` are written by the document loader, not authored
    in a `Source` YAML file — they record what file (by content) is currently
    ingested for this source, so re-ingesting an unchanged file is a no-op and
    re-ingesting a changed one replaces its chunks rather than accumulating
    stale ones alongside the new content (FR-CO-04).

    `structure_scheme`, when non-empty, names a segmenter in
    `mythrix.core.vector.segmentation` (FR-CO-05) that
    the document loader routes ingestion through instead of fixed word-count
    chunking. Empty for a source with no declared structure.
    """

    id: str
    domain: str
    citation_label: str = ""
    title: str
    author: str
    publication_year: int | None = None
    license: str = ""
    uri: str = ""
    description: str = ""
    content_hash: str = ""
    ingested_at: datetime | None = None
    structure_scheme: str = ""


class Property(MythrixModel):
    """A static, structural fact — never used to build retrieval query text (FR-CO-03,
    FR-DM-04), regardless of whether it is attached to a `Sign` (tradition-independent)
    or a `Manifestation` (tradition-specific).
    """

    id: str
    key: str
    value: str
    position: int = 0


class QueryDirective(MythrixModel):
    """A curator-authored retrieval instruction on one `Interpretant` (FR-CO-03, FR-RT-15,
    FR-RT-11, FR-EX-01–05).

    `directive` is a free-text hint, not an enforced enum — v1 code interprets three
    values. `"filter"` marks this interpretant as an exact value: it is excluded from
    the plain concept query text and instead applied as an additional literal-text
    filter, using `as_token`, cross-joined with every other concept in the sign.
    `"exact"` keeps this interpretant in the plain concept query text *and*
    additionally applies a literal-text filter scoped to its own concept only —
    `as_token` is optional here and defaults to `value` when omitted. `"skip"`
    excludes this interpretant from retrieval entirely — no plain query and no
    literal-text filter — while it remains an ordinary fact elsewhere in the Sign
    Graph. `as_token` is required for `"filter"`, optional for `"exact"`, and unused
    for `"skip"`.
    """

    directive: str
    as_token: str = ""


class Interpretant(MythrixModel):
    """A conceptual token, value, or meaning evoked by a sign within one
    manifestation (FR-SD-05) — eligible for retrieval query construction (FR-CO-03)
    unless it carries a `query` directive that says otherwise, in which case it is
    handled as described on `QueryDirective`.

    `type` is a free-text hint for display/organization (e.g. "concept",
    "foundation", "numeric_value") — descriptive metadata only, never part of
    matching identity, which is keyed by `value` alone.
    """

    id: str
    type: str = "concept"
    value: str
    position: int = 0
    query: QueryDirective | None = None


class AdhocTerm(MythrixModel):
    """One user-authored term for an ad-hoc, graph-independent query
    (`specs/interfaces/agnostic-query.md` FR-AQ-02, ADR-010) —
    the raw-input counterpart to a curator-authored `Interpretant`. `directive`
    reuses `QueryDirective`'s `"exact"`/`"filter"` vocabulary; `None` is an
    ordinary concept term."""

    value: str
    directive: Literal["exact", "filter"] | None = None


class Citation(MythrixModel):
    """A citation to a source, from either a manifestation or an intersemiotic
    interpretant."""

    source: Source
    locator: str = ""


class IntersemioticInterpretant(MythrixModel):
    """A typed, attributable correspondence from one sign to another (FR-DM-03, FR-SD-04).

    `according_to` records which tradition/attribution-system asserts this
    specific claim — deliberately the *only* attribution on the edge, since the
    claim is about the signs themselves, not about a specific manifestation of
    either one. This is what lets multiple competing correspondence systems
    coexist without conflicting, and what lets a sign with zero manifestations
    still participate.

    `confidence` is free text, not an enforced enum — e.g. "attributed",
    "traditional", "disputed", "speculative" are suggested starting points for
    curators, but this vocabulary is a documentation convention, not a validated
    closed set.

    `target_interpretants` is *not* part of the correspondence claim itself —
    it's the target sign's own manifestation-level interpretants, gathered
    across every tradition it is manifested under, purely so retrieval query
    construction (FR-CO-03) can draw on what the target itself means. It never
    includes `target_sign.properties` or any manifestation's `properties` —
    properties are never used to build query text, at any scope, reached any way.
    """

    relationship: str
    target_sign: Sign
    according_to: Tradition
    description: str = ""
    symmetric: bool = False
    confidence: str = "attributed"
    target_interpretants: tuple[Interpretant, ...] = ()
    citation: Citation | None = None


class Sign(MythrixModel):
    """A domain-agnostic sign anchor.

    `canonical_name` is an internal/fallback label only — the tradition-specific
    display name actually shown to users lives on `Manifestation.display_name` (FR-DM-02).

    `semiotic_system` names the overarching domain/system this sign belongs to
    (e.g. "tarot_cards", "hebrew_alef_bet") — always present, even for a sign
    with zero manifestations, so an intersemiotic interpretant's target can be
    resolved by name scoped to a named system (FR-SD-03).

    `properties` holds intrinsic, tradition-independent facts about the sign
    itself (e.g. a Hebrew letter's alphabet position or numeric value) — true
    regardless of interpretive lens, unlike `Manifestation.interpretants`, which
    holds tradition-scoped interpretive claims that can genuinely differ by
    tradition.

    `intersemiotic_interpretants` holds this sign's correspondences to other
    signs (FR-DM-03, FR-SD-04). These live on `Sign`, not `Manifestation`, because a
    correspondence claim is about the sign itself, attributed to whichever
    tradition/system asserts it — not about one specific tradition's rendering
    of it — and because a sign with no manifestation at all must still be able
    to participate in a correspondence. Targets are shallow (their own
    `intersemiotic_interpretants` is always `()`) to avoid unbounded recursion;
    only the top-level queried sign has this populated.
    """

    id: str
    slug: str
    canonical_name: str
    sign_type: str
    semiotic_system: str
    notes: str = ""
    properties: tuple[Property, ...] = ()
    intersemiotic_interpretants: tuple[IntersemioticInterpretant, ...] = ()


class Manifestation(MythrixModel):
    """A sign as understood within one tradition — the join entity that keeps
    distinct traditions' meanings from collapsing into one. Intersemiotic
    interpretants to other signs live on `Sign.intersemiotic_interpretants`, not
    here — see `IntersemioticInterpretant`.

    `properties` holds structural facts specific to this one tradition's
    rendering of the sign (e.g. a card's position number within one specific
    deck) — distinct from `Sign.properties` (tradition-independent) and from
    `interpretants` (tradition-scoped but eligible for retrieval).
    """

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
    """A lightweight listing of one sign, for a picker to choose a
    sign/tradition pair guaranteed to have a manifestation (`specs/interfaces/web-viewer.md`
    FR-WEB-01) — not a full `Sign` (no
    `properties`/`intersemiotic_interpretants`), since a picker has no use for
    either.

    `semiotic_system` lets a picker offer a semiotic-system selector that
    scopes which signs it lists (FR-WEB-01)."""

    slug: str
    canonical_name: str
    sign_type: str
    semiotic_system: str
    tradition_slugs: tuple[str, ...] = ()


class GraphFacts(MythrixModel):
    """Deterministic result of a single graph query: one sign, resolved for one
    tradition (v1 query scope, FR-RT-01)."""

    sign: Sign
    manifestation: Manifestation


class SourceFacet(MythrixModel):
    """One Sources-facet option: a corpus source and how many fragments in
    the current result come from it."""

    id: str
    label: str
    count: int


class InterpretantFacet(MythrixModel):
    """One Interpretants-facet option: an interpretant value and how many
    distinct fragments it matched in the current result."""

    value: str
    count: int


class Facets(MythrixModel):
    """Both facet rows for one query result."""

    sources: tuple[SourceFacet, ...] = ()
    interpretants: tuple[InterpretantFacet, ...] = ()


class Segment(MythrixModel):
    """One structurally-bounded constituent unit of a `Region` — a verse or a
    numbered section, verbatim (FR-RK-08). A
    region's `segments` carries each match-carrying segment once, deduped by
    `ordinal`, regardless of how many interpretants matched it.

    `section` names the enclosing chapter/numbered-section locator (e.g.
    `"Genesis 20"`) a source's segmenter attaches to each chunk, empty for a
    source with no declared structure — carried here so a consumer (the web
    viewer's Add Context action, `hotspot-context-expansion`) can tell whether
    a neighboring segment shares this one's chapter without a second lookup.
    """

    ordinal: int
    locator: str
    text: str
    section: str = ""


class Match(MythrixModel):
    """One interpretant's match within a `Region`, anchored to the specific
    constituent `Segment` it hit (`segment_ordinal`) so a consumer can
    navigate directly to where the match occurred rather than re-scanning the
    region (FR-RK-09). `kind` distinguishes a `"concept"` match (dense similarity,
    carries a meaningful `score`) from a literal whole-word-bounded containment
    match (`exact_value=True`, `score` not meaningful) — labeled `"exact"` when
    reached via a `query.directive: "exact"` interpretant (FR-EX-04) or `"filter"`
    when reached via a `query.directive: "filter"` interpretant (FR-EX-05)."""

    interpretant: str
    kind: Literal["concept", "exact", "filter"]
    score: float = 0.0
    exact_value: bool = False
    segment_ordinal: int


class Region(MythrixModel):
    """A contiguous span of one source's segments over which interpretant
    matches converge (FR-RK-01–FR-RK-03) — the ranked,
    scored unit the query path returns. `score` is the specificity-weighted
    convergence score (FR-RK-05);
    `convergence_count` is the number of distinct interpretants matching
    within the region — a region matched by exactly one `"concept"` or
    `"exact"`-directive interpretant (an isolated match) is a valid, rankable
    region (FR-RK-03), not a filtered-out case. A region matched exclusively
    by one or more `"filter"`-directive interpretants never appears here at
    all (FR-RT-20, ADR-017)."""

    region_id: str
    source: Source
    locator: str
    score: float = 0.0
    convergence_count: int = 0
    segments: tuple[Segment, ...] = ()
    matches: tuple[Match, ...] = ()


class RegionQueryResult(MythrixModel):
    """Whole-response shape for the region-centric query endpoint
    (see `ranking.md`) — facets plus a ranked region list."""

    facets: Facets
    regions: tuple[Region, ...] = ()
