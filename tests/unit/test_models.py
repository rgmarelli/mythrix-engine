"""Unit tests for core.models: instantiation, round-trip serialization, and immutability."""

from datetime import UTC, datetime

import pytest

from mythrix.core.models import (
    Attribute,
    Citation,
    GraphFacts,
    Interpretation,
    InterpretationResult,
    RelationshipFact,
    RetrievalContext,
    RetrievedPassage,
    Source,
    Symbol,
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
        title="The Pictorial Key to the Tarot",
        author="Arthur Edward Waite",
        publication_year=1910,
        license="public-domain",
        uri="https://www.sacred-texts.com/tarot/pkt/index.htm",
    )


@pytest.fixture
def the_tower_symbol() -> Symbol:
    return Symbol(
        id="the-tower",
        slug="the-tower",
        canonical_name="The Tower",
        symbol_type="major-arcana",
        notes="Sixteenth trump of the standard 78-card tarot deck.",
    )


@pytest.fixture
def hebrew_letter_peh_symbol() -> Symbol:
    return Symbol(
        id="hebrew-letter-peh",
        slug="hebrew-letter-peh",
        canonical_name="Peh",
        symbol_type="hebrew-letter",
        properties=(
            Attribute(id="peh-prop-position", key="alphabet_position", value="17"),
            Attribute(id="peh-prop-numeric", key="numeric_value", value="80"),
        ),
    )


def test_symbol_properties_round_trip(hebrew_letter_peh_symbol: Symbol) -> None:
    dumped = hebrew_letter_peh_symbol.model_dump(mode="json")
    restored = Symbol.model_validate(dumped)

    assert restored == hebrew_letter_peh_symbol
    assert {p.key for p in restored.properties} == {"alphabet_position", "numeric_value"}


def test_interpretation_round_trip(
    rider_waite: Tradition,
    waite_source: Source,
    the_tower_symbol: Symbol,
) -> None:
    citation = Citation(source=waite_source, locator="p. 143")
    attribute = Attribute(id="attr-1", key="element", value="Fire")
    interpretation = Interpretation(
        id="the-tower::rider-waite",
        symbol_id="the-tower",
        tradition=rider_waite,
        display_name="The Tower",
        summary="Sudden upheaval; the collapse of false structures.",
        attributes=(attribute,),
        citations=(citation,),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    dumped = interpretation.model_dump(mode="json")
    restored = Interpretation.model_validate(dumped)

    assert restored == interpretation
    assert restored.attributes[0].key == "element"


def test_symbol_relationships_round_trip(
    golden_dawn_kabbalah: Tradition,
    waite_source: Source,
    the_tower_symbol: Symbol,
    hebrew_letter_peh_symbol: Symbol,
) -> None:
    """Correspondences live on Symbol.relationships, not Interpretation — a claim is
    about the symbols themselves, attributed to whichever tradition asserts it, not
    tied to one specific interpretation of either endpoint (FR3, FR19)."""
    citation = Citation(source=waite_source, locator="p. 143")
    relationship = RelationshipFact(
        relationship_type="corresponds_to_letter",
        target_symbol=hebrew_letter_peh_symbol,
        according_to_tradition=golden_dawn_kabbalah,
        description="Golden Dawn attributes The Tower to the Hebrew letter Peh.",
        citation=citation,
    )
    the_tower_with_relationship = the_tower_symbol.model_copy(update={"relationships": (relationship,)})

    dumped = the_tower_with_relationship.model_dump(mode="json")
    restored = Symbol.model_validate(dumped)

    assert restored == the_tower_with_relationship
    assert restored.relationships[0].according_to_tradition.slug == "golden-dawn-kabbalah"
    assert restored.relationships[0].target_symbol.slug == "hebrew-letter-peh"


def test_interpretation_result_round_trip(
    rider_waite: Tradition,
    waite_source: Source,
    the_tower_symbol: Symbol,
) -> None:
    interpretation = Interpretation(
        id="the-tower::rider-waite",
        symbol_id="the-tower",
        tradition=rider_waite,
        display_name="The Tower",
        summary="Sudden upheaval; the collapse of false structures.",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    passage = RetrievedPassage(
        chunk_id="chunk-12",
        source=waite_source,
        tradition=rider_waite,
        text="The Tower: This card represents sudden upheaval and the collapse of false structures.",
        locator="p. 143",
        score=0.87,
        chunk_index=12,
        embedding_model="nomic-embed-text",
    )
    context = RetrievalContext(
        graph_facts=GraphFacts(symbol=the_tower_symbol, interpretation=interpretation),
        passages=(passage,),
    )
    result = InterpretationResult(
        context=context,
        narrative="The Tower represents sudden upheaval [G1]. Waite associates it with catastrophe [S1].",
        generation_model="llama3.1",
        embedding_model="nomic-embed-text",
        citation_markers_valid=True,
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    dumped = result.model_dump(mode="json")
    restored = InterpretationResult.model_validate(dumped)

    assert restored == result
    assert restored.context.passages[0].text == passage.text


def test_models_are_frozen(rider_waite: Tradition) -> None:
    with pytest.raises(Exception):  # noqa: B017 — pydantic raises a ValidationError subclass
        rider_waite.name = "Something Else"


def test_interpretation_result_derived_update_uses_model_copy(
    rider_waite: Tradition,
    the_tower_symbol: Symbol,
) -> None:
    interpretation = Interpretation(
        id="the-tower::rider-waite",
        symbol_id="the-tower",
        tradition=rider_waite,
        display_name="The Tower",
        summary="Sudden upheaval.",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    context = RetrievalContext(graph_facts=GraphFacts(symbol=the_tower_symbol, interpretation=interpretation))
    result = InterpretationResult(
        context=context,
        narrative="Draft narrative [S9].",
        generation_model="llama3.1",
        embedding_model="nomic-embed-text",
        citation_markers_valid=False,
        invalid_markers=("[S9]",),
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    validated = result.model_copy(update={"citation_markers_valid": True, "invalid_markers": ()})

    assert result.citation_markers_valid is False
    assert validated.citation_markers_valid is True
    assert validated.invalid_markers == ()
