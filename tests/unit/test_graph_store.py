"""Unit tests for KuzuGraphStore: idempotent upserts and deterministic retrieval (T9)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mythrix.core.errors import InterpretationNotFoundError, SymbolNotFoundError, TraditionNotFoundError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import Attribute, Citation, Interpretation, Source, Symbol, Tradition

CREATED_AT = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> KuzuGraphStore:
    return KuzuGraphStore(tmp_path / "graph.kuzu")


def _seed_fixture(store: KuzuGraphStore) -> None:
    rider_waite = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")
    golden_dawn = Tradition(
        id="golden-dawn-kabbalah", slug="golden-dawn-kabbalah", name="Golden Dawn Kabbalah", domain="kabbalah"
    )
    pre_golden_dawn = Tradition(
        id="pre-golden-dawn", slug="pre-golden-dawn", name="Pre-Golden-Dawn Correspondence", domain="kabbalah"
    )
    waite_source = Source(id="waite-pictorial-key", title="The Pictorial Key to the Tarot", author="A. E. Waite")

    for tradition in (rider_waite, golden_dawn, pre_golden_dawn):
        store.upsert_tradition(tradition)
    store.upsert_source(waite_source)

    the_tower = Symbol(id="the-tower", slug="the-tower", canonical_name="The Tower", symbol_type="major-arcana")
    the_tower_interpretation = Interpretation(
        id="the-tower::rider-waite",
        symbol_id="the-tower",
        tradition=rider_waite,
        display_name="The Tower",
        summary="Sudden upheaval; the collapse of false structures.",
        attributes=(Attribute(id="attr-element", key="element", value="Fire"),),
        citations=(Citation(source=waite_source, locator="p. 143"),),
        created_at=CREATED_AT,
    )
    store.upsert_symbol_with_interpretation(the_tower, the_tower_interpretation)

    peh = Symbol(
        id="hebrew-letter-peh",
        slug="hebrew-letter-peh",
        canonical_name="Peh",
        symbol_type="hebrew-letter",
        properties=(
            Attribute(id="peh-prop-position", key="alphabet_position", value="17"),
            Attribute(id="peh-prop-numeric", key="numeric_value", value="80"),
        ),
    )
    peh_interpretation = Interpretation(
        id="hebrew-letter-peh::golden-dawn-kabbalah",
        symbol_id="hebrew-letter-peh",
        tradition=golden_dawn,
        display_name="Peh",
        summary="",
        created_at=CREATED_AT,
    )
    store.upsert_symbol_with_interpretation(peh, peh_interpretation)

    ayin = Symbol(
        id="hebrew-letter-ayin", slug="hebrew-letter-ayin", canonical_name="Ayin", symbol_type="hebrew-letter"
    )
    ayin_interpretation = Interpretation(
        id="hebrew-letter-ayin::pre-golden-dawn",
        symbol_id="hebrew-letter-ayin",
        tradition=pre_golden_dawn,
        display_name="Ayin",
        summary="",
        created_at=CREATED_AT,
    )
    store.upsert_symbol_with_interpretation(ayin, ayin_interpretation)

    # A pure correspondence target with zero interpretations — must still be a valid
    # RELATES_TO endpoint now that the edge connects Symbol -> Symbol directly.
    path_tiphareth_yesod = Symbol(
        id="path-tiphareth-yesod",
        slug="path-tiphareth-yesod",
        canonical_name="Path: Tiphareth-Yesod",
        symbol_type="tree-of-life-path",
    )
    store.upsert_symbol(path_tiphareth_yesod)

    store.upsert_relationship(
        from_symbol_id="the-tower",
        to_symbol_id="hebrew-letter-peh",
        relationship_type="corresponds_to_letter",
        according_to_tradition_id="golden-dawn-kabbalah",
        description="Golden Dawn attributes The Tower to the Hebrew letter Peh.",
        source_id="waite-pictorial-key",
    )
    store.upsert_relationship(
        from_symbol_id="the-tower",
        to_symbol_id="hebrew-letter-ayin",
        relationship_type="corresponds_to_letter",
        according_to_tradition_id="pre-golden-dawn",
        description="An earlier correspondence system assigns a different letter.",
    )
    store.upsert_relationship(
        from_symbol_id="hebrew-letter-peh",
        to_symbol_id="path-tiphareth-yesod",
        relationship_type="tree_of_life_path",
        according_to_tradition_id="golden-dawn-kabbalah",
    )


def test_get_interpretation_returns_expected_graph_facts(store: KuzuGraphStore) -> None:
    _seed_fixture(store)

    facts = store.get_interpretation("the-tower", "rider-waite")

    assert facts.symbol.slug == "the-tower"
    assert facts.interpretation.display_name == "The Tower"
    assert facts.interpretation.tradition.slug == "rider-waite"

    assert len(facts.interpretation.attributes) == 1
    assert facts.interpretation.attributes[0].key == "element"
    assert facts.interpretation.attributes[0].value == "Fire"

    assert len(facts.interpretation.citations) == 1
    assert facts.interpretation.citations[0].source.title == "The Pictorial Key to the Tarot"
    assert facts.interpretation.citations[0].locator == "p. 143"

    relationships = {r.according_to_tradition.slug: r for r in facts.symbol.relationships}
    assert set(relationships) == {"golden-dawn-kabbalah", "pre-golden-dawn"}
    assert relationships["golden-dawn-kabbalah"].target_symbol.slug == "hebrew-letter-peh"
    assert relationships["golden-dawn-kabbalah"].citation is not None
    assert relationships["golden-dawn-kabbalah"].citation.source.id == "waite-pictorial-key"
    assert relationships["pre-golden-dawn"].target_symbol.slug == "hebrew-letter-ayin"
    assert relationships["pre-golden-dawn"].citation is None

    # Peh's intrinsic properties (alphabet position, numeric value) travel with it as
    # a target_symbol, distinct from any tradition's interpretation of it.
    peh_properties = {p.key: p.value for p in relationships["golden-dawn-kabbalah"].target_symbol.properties}
    assert peh_properties == {"alphabet_position": "17", "numeric_value": "80"}


def test_relationship_target_semantic_facts_gather_its_own_interpretation_attributes(
    store: KuzuGraphStore,
) -> None:
    """`target_semantic_facts` pulls in the target symbol's own interpretation
    attributes (across whichever tradition it's interpreted under) — not just
    its bare `properties` — so retrieval query construction (FR8) can draw on
    what the target itself *means* (e.g. a Hebrew letter's Sepher Yetzirah
    foundation), not only intrinsic facts like its numeric value."""
    _seed_fixture(store)
    golden_dawn = Tradition(
        id="golden-dawn-kabbalah", slug="golden-dawn-kabbalah", name="Golden Dawn Kabbalah", domain="kabbalah"
    )
    peh_with_meaning = Symbol(
        id="hebrew-letter-peh",
        slug="hebrew-letter-peh",
        canonical_name="Peh",
        symbol_type="hebrew-letter",
        properties=(
            Attribute(id="peh-prop-position", key="alphabet_position", value="17"),
            Attribute(id="peh-prop-numeric", key="numeric_value", value="80"),
        ),
    )
    peh_interpretation = Interpretation(
        id="hebrew-letter-peh::golden-dawn-kabbalah",
        symbol_id="hebrew-letter-peh",
        tradition=golden_dawn,
        display_name="Peh",
        summary="",
        attributes=(Attribute(id="peh-attr-meaning", key="meaning", value="Mouth"),),
        created_at=CREATED_AT,
    )
    store.upsert_symbol_with_interpretation(peh_with_meaning, peh_interpretation)

    facts = store.get_interpretation("the-tower", "rider-waite")
    peh_relationship = next(r for r in facts.symbol.relationships if r.target_symbol.slug == "hebrew-letter-peh")

    assert {a.key: a.value for a in peh_relationship.target_semantic_facts} == {"meaning": "Mouth"}
    # Peh's own properties are unaffected — the two stay on separate fields.
    assert {p.key for p in peh_relationship.target_symbol.properties} == {"alphabet_position", "numeric_value"}


def test_relationship_target_with_zero_interpretations_is_valid(store: KuzuGraphStore) -> None:
    """A symbol (Path: Tiphareth-Yesod) with no Interpretation at all must still be a
    valid RELATES_TO endpoint, now that the edge connects Symbol -> Symbol directly."""
    _seed_fixture(store)

    peh_facts = store.get_interpretation("hebrew-letter-peh", "golden-dawn-kabbalah")

    assert len(peh_facts.symbol.relationships) == 1
    path_relationship = peh_facts.symbol.relationships[0]
    assert path_relationship.target_symbol.slug == "path-tiphareth-yesod"
    assert path_relationship.target_symbol.canonical_name == "Path: Tiphareth-Yesod"


def test_upserts_are_idempotent(store: KuzuGraphStore) -> None:
    _seed_fixture(store)
    _seed_fixture(store)  # re-run everything with identical data

    facts = store.get_interpretation("the-tower", "rider-waite")

    assert len(facts.interpretation.attributes) == 1
    assert len(facts.interpretation.citations) == 1
    assert len(facts.symbol.relationships) == 2

    peh_target = next(r for r in facts.symbol.relationships if r.target_symbol.slug == "hebrew-letter-peh")
    assert len(peh_target.target_symbol.properties) == 2


def test_reupserting_with_a_renamed_interpretation_attribute_key_leaves_no_stale_one(store: KuzuGraphStore) -> None:
    """An Attribute's id is derived from its key (symbol_loader.py), so a curator
    renaming one in the YAML (e.g. `assignation` -> `planet`) must not leave the
    old key's Attribute node orphaned but still linked (a real bug found via a
    live query text unexpectedly containing both the old and new key)."""
    _seed_fixture(store)
    rider_waite = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")
    the_tower = Symbol(id="the-tower", slug="the-tower", canonical_name="The Tower", symbol_type="major-arcana")
    renamed_interpretation = Interpretation(
        id="the-tower::rider-waite",
        symbol_id="the-tower",
        tradition=rider_waite,
        display_name="The Tower",
        summary="Sudden upheaval; the collapse of false structures.",
        attributes=(Attribute(id="attr-primary-element", key="primary_element", value="Fire"),),
        created_at=CREATED_AT,
    )

    store.upsert_symbol_with_interpretation(the_tower, renamed_interpretation)

    facts = store.get_interpretation("the-tower", "rider-waite")
    assert [a.key for a in facts.interpretation.attributes] == ["primary_element"]


def test_reupserting_with_a_renamed_symbol_property_key_leaves_no_stale_one(store: KuzuGraphStore) -> None:
    """Same reconciliation, for `Symbol.properties` this time."""
    _seed_fixture(store)
    renamed_peh = Symbol(
        id="hebrew-letter-peh",
        slug="hebrew-letter-peh",
        canonical_name="Peh",
        symbol_type="hebrew-letter",
        properties=(Attribute(id="peh-prop-gematria", key="gematria_value", value="80"),),
    )

    store.upsert_symbol(renamed_peh)

    facts = store.get_interpretation("the-tower", "rider-waite")
    peh = next(r for r in facts.symbol.relationships if r.target_symbol.slug == "hebrew-letter-peh").target_symbol
    assert [p.key for p in peh.properties] == ["gematria_value"]


def test_symbol_properties_are_distinct_from_interpretation_attributes(store: KuzuGraphStore) -> None:
    """Intrinsic Symbol.properties (HAS_ATTRIBUTE from Symbol) must not be conflated
    with tradition-scoped Interpretation.attributes (HAS_ATTRIBUTE from Interpretation),
    even though both reuse the same Attribute node table and rel table."""
    _seed_fixture(store)

    facts = store.get_interpretation("the-tower", "rider-waite")
    peh = next(r for r in facts.symbol.relationships if r.target_symbol.slug == "hebrew-letter-peh").target_symbol

    assert {p.key for p in peh.properties} == {"alphabet_position", "numeric_value"}
    # the-tower's own interpretation-level attribute ("element") must not leak onto Peh
    assert "element" not in {p.key for p in peh.properties}


def test_symbol_not_found_raises(store: KuzuGraphStore) -> None:
    _seed_fixture(store)
    with pytest.raises(SymbolNotFoundError):
        store.get_interpretation("nonexistent-symbol", "rider-waite")


def test_tradition_not_found_raises(store: KuzuGraphStore) -> None:
    _seed_fixture(store)
    with pytest.raises(TraditionNotFoundError):
        store.get_interpretation("the-tower", "nonexistent-tradition")


def test_interpretation_not_found_raises_when_symbol_and_tradition_exist_but_unlinked(store: KuzuGraphStore) -> None:
    _seed_fixture(store)
    with pytest.raises(InterpretationNotFoundError):
        store.get_interpretation("the-tower", "golden-dawn-kabbalah")


def test_list_traditions_returns_every_tradition_sorted_by_slug(store: KuzuGraphStore) -> None:
    _seed_fixture(store)
    traditions = store.list_traditions()
    assert [t.slug for t in traditions] == ["golden-dawn-kabbalah", "pre-golden-dawn", "rider-waite"]


def test_list_symbols_excludes_symbols_with_zero_interpretations(store: KuzuGraphStore) -> None:
    _seed_fixture(store)
    summaries = {s.slug: s for s in store.list_symbols()}
    assert "path-tiphareth-yesod" not in summaries
    assert set(summaries) == {"the-tower", "hebrew-letter-peh", "hebrew-letter-ayin"}


def test_list_symbols_reports_every_tradition_a_symbol_is_interpreted_in(store: KuzuGraphStore) -> None:
    _seed_fixture(store)
    the_tower = next(s for s in store.list_symbols() if s.slug == "the-tower")
    assert the_tower.canonical_name == "The Tower"
    assert the_tower.symbol_type == "major-arcana"
    assert the_tower.tradition_slugs == ("rider-waite",)
