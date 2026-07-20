"""Unit tests for core.models: instantiation, round-trip serialization, and immutability."""

from datetime import UTC, datetime

import pytest

from mythrix.core.models import (
    Citation,
    ConceptCandidates,
    ConceptMatchScore,
    ConceptPairCandidates,
    GraphFacts,
    Interpretant,
    IntersemioticInterpretant,
    Manifestation,
    MergedCandidate,
    Property,
    QueryDirective,
    RetrievalContext,
    RetrievedPassage,
    Sign,
    Source,
    Tradition,
)


@pytest.fixture
def rider_waite() -> Tradition:
    return Tradition(
        id="rider-waite",
        slug="rider-waite",
        name="Rider-Waite-Smith",
        domain="tarot",
        description="The tradition established by Waite and Smith's 1909 deck.",
    )


@pytest.fixture
def golden_dawn_kabbalah() -> Tradition:
    return Tradition(
        id="golden-dawn-kabbalah",
        slug="golden-dawn-kabbalah",
        name="Golden Dawn Hermetic Kabbalah",
        domain="kabbalah",
    )


@pytest.fixture
def waite_source() -> Source:
    return Source(
        id="waite-pictorial-key",
        domain="tarot",
        title="The Pictorial Key to the Tarot",
        author="Arthur Edward Waite",
        publication_year=1910,
        license="public-domain",
        uri="https://www.sacred-texts.com/tarot/pkt/index.htm",
    )


@pytest.fixture
def the_tower_sign() -> Sign:
    return Sign(
        id="the-tower",
        slug="the-tower",
        canonical_name="The Tower",
        sign_type="major-arcana",
        semiotic_system="tarot",
        notes="Sixteenth trump of the standard 78-card tarot deck.",
    )


@pytest.fixture
def hebrew_letter_peh_sign() -> Sign:
    return Sign(
        id="hebrew-letter-peh",
        slug="hebrew-letter-peh",
        canonical_name="Peh",
        sign_type="hebrew-letter",
        semiotic_system="hebrew_alef_bet",
        properties=(
            Property(id="peh-prop-position", key="alphabet_position", value="17"),
            Property(id="peh-prop-numeric", key="numeric_value", value="80"),
        ),
    )


def test_sign_properties_round_trip(hebrew_letter_peh_sign: Sign) -> None:
    dumped = hebrew_letter_peh_sign.model_dump(mode="json")
    restored = Sign.model_validate(dumped)

    assert restored == hebrew_letter_peh_sign
    assert {p.key for p in restored.properties} == {"alphabet_position", "numeric_value"}


def test_manifestation_round_trip(
    rider_waite: Tradition,
    waite_source: Source,
    the_tower_sign: Sign,
) -> None:
    citation = Citation(source=waite_source, locator="p. 143")
    interpretant = Interpretant(id="interp-1", type="element", value="Fire")
    manifestation = Manifestation(
        id="the-tower::rider-waite",
        sign_id="the-tower",
        tradition=rider_waite,
        display_name="The Tower",
        denotation="Sudden upheaval; the collapse of false structures.",
        interpretants=(interpretant,),
        citations=(citation,),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    dumped = manifestation.model_dump(mode="json")
    restored = Manifestation.model_validate(dumped)

    assert restored == manifestation
    assert restored.interpretants[0].type == "element"


def test_interpretant_query_directive_round_trip() -> None:
    """FR28: an interpretant carrying a `query.directive: filter` annotation
    round-trips its `as_token` alongside — this is the curator-authored
    replacement for the old code-side numeric-value detection."""
    interpretant = Interpretant(
        id="interp-numeric",
        type="numeric_value",
        value="100",
        query=QueryDirective(directive="filter", as_token="hundred"),
    )

    dumped = interpretant.model_dump(mode="json")
    restored = Interpretant.model_validate(dumped)

    assert restored == interpretant
    assert restored.query is not None
    assert restored.query.as_token == "hundred"


def test_interpretant_skip_directive_defaults_as_token_to_empty_string() -> None:
    """FR30: a `"skip"` directive has no use for `as_token` — it's optional,
    not required like `"filter"`'s."""
    interpretant = Interpretant(
        id="interp-meaning", type="meaning", value="eye of the needle", query=QueryDirective(directive="skip")
    )

    assert interpretant.query is not None
    assert interpretant.query.as_token == ""


def test_property_has_no_retrievable_field() -> None:
    """Properties are never used to build retrieval query text regardless of
    scope — there is no per-fact opt-out flag left to set (unlike the retired
    `Attribute.retrievable`)."""
    prop = Property(id="p1", key="letter_type", value="simple")
    assert not hasattr(prop, "retrievable")


def test_sign_intersemiotic_interpretants_round_trip(
    golden_dawn_kabbalah: Tradition,
    waite_source: Source,
    the_tower_sign: Sign,
    hebrew_letter_peh_sign: Sign,
) -> None:
    """Intersemiotic interpretants live on Sign.intersemiotic_interpretants, not
    Manifestation — a claim is about the signs themselves, attributed to
    whichever tradition asserts it, not tied to one specific manifestation of
    either endpoint (FR3, FR19)."""
    citation = Citation(source=waite_source, locator="p. 143")
    interpretant = IntersemioticInterpretant(
        relationship="corresponds_to_letter",
        target_sign=hebrew_letter_peh_sign,
        according_to=golden_dawn_kabbalah,
        description="Golden Dawn attributes The Tower to the Hebrew letter Peh.",
        citation=citation,
    )
    the_tower_with_interpretant = the_tower_sign.model_copy(update={"intersemiotic_interpretants": (interpretant,)})

    dumped = the_tower_with_interpretant.model_dump(mode="json")
    restored = Sign.model_validate(dumped)

    assert restored == the_tower_with_interpretant
    assert restored.intersemiotic_interpretants[0].according_to.slug == "golden-dawn-kabbalah"
    assert restored.intersemiotic_interpretants[0].target_sign.slug == "hebrew-letter-peh"


def test_concept_candidates_round_trip_and_flatten_via_all_passages(
    rider_waite: Tradition,
    waite_source: Source,
    the_tower_sign: Sign,
) -> None:
    """`ConceptCandidates` groups passages by concept (FR24) rather than one
    flat list — `RetrievalContext.all_passages` flattens across every concept
    for callers that only need a corpus-wide view."""
    manifestation = Manifestation(
        id="the-tower::rider-waite",
        sign_id="the-tower",
        tradition=rider_waite,
        display_name="The Tower",
        denotation="Sudden upheaval; the collapse of false structures.",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    passage_fire = RetrievedPassage(
        chunk_id="chunk-12",
        source=waite_source,
        text="The Tower: This card represents sudden upheaval and the collapse of false structures.",
        locator="p. 143",
        score=0.87,
        chunk_index=12,
        embedding_model="nomic-embed-text",
    )
    passage_ruin = RetrievedPassage(
        chunk_id="chunk-13",
        source=waite_source,
        text="Ruin comes suddenly, as if by a bolt from the blue.",
        score=0.61,
        chunk_index=13,
        embedding_model="nomic-embed-text",
    )
    context = RetrievalContext(
        graph_facts=GraphFacts(sign=the_tower_sign, manifestation=manifestation),
        concept_candidates=(
            ConceptCandidates(concept="Fire", passages=(passage_fire,)),
            ConceptCandidates(concept="ruin", passages=(passage_ruin,)),
        ),
    )

    dumped = context.model_dump(mode="json")
    restored = RetrievalContext.model_validate(dumped)

    assert restored == context
    assert restored.concept_candidates[0].concept == "Fire"
    assert restored.all_passages == (passage_fire, passage_ruin)


def test_concept_pair_candidates_round_trip(
    rider_waite: Tradition,
    waite_source: Source,
    the_tower_sign: Sign,
) -> None:
    """FR27/FR28: a `ConceptPairCandidates` group carries the two concepts it
    converges on, and each candidate carries its per-concept match scores —
    including an exact-value match (FR28), which carries no score of its
    own, only a `document_contains`-guaranteed membership."""
    manifestation = Manifestation(
        id="the-tower::rider-waite",
        sign_id="the-tower",
        tradition=rider_waite,
        display_name="The Tower",
        denotation="Sudden upheaval; the collapse of false structures.",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    passage = RetrievedPassage(
        chunk_id="chunk-12",
        source=waite_source,
        text="And Abraham was a hundred years old, when Isaac his son was born to him.",
        locator="Genesis 21:5",
        score=0.61,
        chunk_index=12,
        embedding_model="nomic-embed-text",
    )
    merged_candidate = MergedCandidate(
        passage=passage,
        matches=(
            ConceptMatchScore(concept="child", score=0.55),
            ConceptMatchScore(concept="100", score=0.0, exact_value=True),
        ),
        combined_score=0.55,
    )
    pair_candidates = ConceptPairCandidates(concepts=("child", "100"), candidates=(merged_candidate,))
    context = RetrievalContext(
        graph_facts=GraphFacts(sign=the_tower_sign, manifestation=manifestation),
        pair_candidates=(pair_candidates,),
    )

    dumped = context.model_dump(mode="json")
    restored = RetrievalContext.model_validate(dumped)

    assert restored == context
    assert restored.pair_candidates[0].concepts == ("child", "100")
    assert restored.pair_candidates[0].candidates[0].matches[1].exact_value is True
    # `all_passages` deliberately doesn't include pair-only convergences — see
    # its docstring on why `pair_candidates` isn't a strict subset.
    assert context.all_passages == ()


def test_models_are_frozen(rider_waite: Tradition) -> None:
    with pytest.raises(Exception):  # noqa: B017 — pydantic raises a ValidationError subclass
        rider_waite.name = "Something Else"


def test_retrieval_context_derived_update_uses_model_copy(
    rider_waite: Tradition,
    the_tower_sign: Sign,
) -> None:
    manifestation = Manifestation(
        id="the-tower::rider-waite",
        sign_id="the-tower",
        tradition=rider_waite,
        display_name="The Tower",
        denotation="Sudden upheaval.",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    context = RetrievalContext(graph_facts=GraphFacts(sign=the_tower_sign, manifestation=manifestation))

    updated = context.model_copy(update={"pair_candidates": (ConceptPairCandidates(concepts=("a", "b")),)})

    assert context.pair_candidates == ()
    assert updated.pair_candidates[0].concepts == ("a", "b")
