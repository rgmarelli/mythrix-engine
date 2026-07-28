"""Unit tests for core.models: instantiation, round-trip serialization, and immutability."""

from datetime import UTC, datetime

import pytest

from mythrix.core.models import (
    Citation,
    Facets,
    Interpretant,
    IntersemioticInterpretant,
    Manifestation,
    Match,
    Property,
    QueryDirective,
    Region,
    RegionQueryResult,
    Segment,
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
    """FR-RT-09: an interpretant carrying a `query.directive: filter` annotation
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
    """FR-RT-11: a `"skip"` directive has no use for `as_token` — it's optional,
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
    either endpoint (FR-DM-03, FR-SD-04)."""
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


def test_region_round_trip_anchors_matches_to_their_segments(waite_source: Source) -> None:
    """T8: the settled `Region`/`Segment`/`Match` shape (FR-RK-08–FR-RK-10) — a
    region's `segments` carry each match-carrying verse's text once, and
    every match (concept or exact) carries the `segment_ordinal` of the
    specific verse it hit, matching plan.md's worked Genesis 21:5/21:6
    contract."""
    genesis_source = waite_source.model_copy(update={"id": "en_drb", "domain": "scripture", "title": "DRB"})
    segment_5 = Segment(ordinal=104, locator="Genesis 21:5", text="And Abraham was a hundred years old.")
    segment_6 = Segment(ordinal=105, locator="Genesis 21:6", text="And Sara said: God hath made a laughter for me.")
    region = Region(
        region_id="en_drb::104-105",
        source=genesis_source,
        locator="Genesis 21:5-6",
        score=6.18,
        convergence_count=2,
        segments=(segment_5, segment_6),
        matches=(
            Match(interpretant="hundred", kind="concept", score=0.71, segment_ordinal=104),
            Match(interpretant="laughter", kind="concept", score=0.68, segment_ordinal=105),
        ),
    )

    dumped = region.model_dump(mode="json")
    restored = Region.model_validate(dumped)

    assert restored == region
    assert {s.text for s in restored.segments} == {segment_5.text, segment_6.text}
    assert restored.matches[0].segment_ordinal == 104
    assert restored.matches[1].segment_ordinal == 105


def test_exact_match_carries_no_meaningful_score() -> None:
    match = Match(interpretant="hundred", kind="exact", exact_value=True, segment_ordinal=104)

    assert match.score == 0.0
    assert match.exact_value is True


def test_filter_match_carries_no_meaningful_score() -> None:
    """FR-EX-05: a `"filter"`-directive hit is labeled `kind="filter"`,
    distinct from `"exact"` (reserved for a `query.directive: "exact"` hit)."""
    match = Match(interpretant="hundred", kind="filter", exact_value=True, segment_ordinal=104)

    assert match.score == 0.0
    assert match.exact_value is True


def test_region_query_result_round_trip(waite_source: Source) -> None:
    region = Region(
        region_id="en_drb::104",
        source=waite_source,
        locator="Genesis 21:5",
        matches=(Match(interpretant="hundred", kind="concept", score=0.71, segment_ordinal=104),),
    )
    result = RegionQueryResult(facets=Facets(), regions=(region,))

    dumped = result.model_dump(mode="json")
    restored = RegionQueryResult.model_validate(dumped)

    assert restored == result


def test_models_are_frozen(rider_waite: Tradition) -> None:
    with pytest.raises(Exception):  # noqa: B017 — pydantic raises a ValidationError subclass
        rider_waite.name = "Something Else"


def test_derived_update_uses_model_copy(waite_source: Source) -> None:
    region = Region(region_id="en_drb::104", source=waite_source, locator="Genesis 21:5")
    result = RegionQueryResult(facets=Facets())

    updated = result.model_copy(update={"regions": (region,)})

    assert result.regions == ()
    assert updated.regions[0].region_id == "en_drb::104"
