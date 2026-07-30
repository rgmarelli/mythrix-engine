# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for KuzuGraphStore: idempotent upserts and deterministic retrieval (T9)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mythrix.core.errors import ManifestationNotFoundError, SignNotFoundError, TraditionNotFoundError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import Citation, Interpretant, Manifestation, Property, Sign, Source, Tradition

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
    waite_source = Source(
        id="waite-pictorial-key", domain="tarot", title="The Pictorial Key to the Tarot", author="A. E. Waite"
    )

    for tradition in (rider_waite, golden_dawn, pre_golden_dawn):
        store.upsert_tradition(tradition)
    store.upsert_source(waite_source)

    the_tower = Sign(
        id="the-tower",
        slug="the-tower",
        canonical_name="The Tower",
        sign_type="major-arcana",
        semiotic_system="tarot",
    )
    the_tower_manifestation = Manifestation(
        id="the-tower::rider-waite",
        sign_id="the-tower",
        tradition=rider_waite,
        display_name="The Tower",
        denotation="Sudden upheaval; the collapse of false structures.",
        interpretants=(Interpretant(id="interp-element", type="element", value="Fire"),),
        citations=(Citation(source=waite_source, locator="p. 143"),),
        created_at=CREATED_AT,
    )
    store.upsert_sign_with_manifestation(the_tower, the_tower_manifestation)

    peh = Sign(
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
    peh_manifestation = Manifestation(
        id="hebrew-letter-peh::golden-dawn-kabbalah",
        sign_id="hebrew-letter-peh",
        tradition=golden_dawn,
        display_name="Peh",
        created_at=CREATED_AT,
    )
    store.upsert_sign_with_manifestation(peh, peh_manifestation)

    ayin = Sign(
        id="hebrew-letter-ayin",
        slug="hebrew-letter-ayin",
        canonical_name="Ayin",
        sign_type="hebrew-letter",
        semiotic_system="hebrew_alef_bet",
    )
    ayin_manifestation = Manifestation(
        id="hebrew-letter-ayin::pre-golden-dawn",
        sign_id="hebrew-letter-ayin",
        tradition=pre_golden_dawn,
        display_name="Ayin",
        created_at=CREATED_AT,
    )
    store.upsert_sign_with_manifestation(ayin, ayin_manifestation)

    # A pure correspondence target with zero manifestations — must still be a valid
    # INTERSEMIOTIC endpoint now that the edge connects Sign -> Sign directly.
    path_tiphareth_yesod = Sign(
        id="path-tiphareth-yesod",
        slug="path-tiphareth-yesod",
        canonical_name="Path: Tiphareth-Yesod",
        sign_type="tree-of-life-path",
        semiotic_system="hebrew_alef_bet",
    )
    store.upsert_sign(path_tiphareth_yesod)

    store.upsert_intersemiotic_interpretant(
        from_sign_id="the-tower",
        to_sign_id="hebrew-letter-peh",
        relationship="corresponds_to_letter",
        according_to_id="golden-dawn-kabbalah",
        description="Golden Dawn attributes The Tower to the Hebrew letter Peh.",
        source_id="waite-pictorial-key",
    )
    store.upsert_intersemiotic_interpretant(
        from_sign_id="the-tower",
        to_sign_id="hebrew-letter-ayin",
        relationship="corresponds_to_letter",
        according_to_id="pre-golden-dawn",
        description="An earlier correspondence system assigns a different letter.",
    )
    store.upsert_intersemiotic_interpretant(
        from_sign_id="hebrew-letter-peh",
        to_sign_id="path-tiphareth-yesod",
        relationship="tree_of_life_path",
        according_to_id="golden-dawn-kabbalah",
    )


def test_get_manifestation_returns_expected_graph_facts(store: KuzuGraphStore) -> None:
    _seed_fixture(store)

    facts = store.get_manifestation("the-tower", "rider-waite")

    assert facts.sign.slug == "the-tower"
    assert facts.manifestation.display_name == "The Tower"
    assert facts.manifestation.tradition.slug == "rider-waite"

    assert len(facts.manifestation.interpretants) == 1
    assert facts.manifestation.interpretants[0].type == "element"
    assert facts.manifestation.interpretants[0].value == "Fire"

    assert len(facts.manifestation.citations) == 1
    assert facts.manifestation.citations[0].source.title == "The Pictorial Key to the Tarot"
    assert facts.manifestation.citations[0].locator == "p. 143"

    interpretants = {i.according_to.slug: i for i in facts.sign.intersemiotic_interpretants}
    assert set(interpretants) == {"golden-dawn-kabbalah", "pre-golden-dawn"}
    assert interpretants["golden-dawn-kabbalah"].target_sign.slug == "hebrew-letter-peh"
    assert interpretants["golden-dawn-kabbalah"].citation is not None
    assert interpretants["golden-dawn-kabbalah"].citation.source.id == "waite-pictorial-key"
    assert interpretants["pre-golden-dawn"].target_sign.slug == "hebrew-letter-ayin"
    assert interpretants["pre-golden-dawn"].citation is None

    # Peh's intrinsic properties (alphabet position, numeric value) travel with it as
    # a target_sign, distinct from any tradition's manifestation of it.
    peh_properties = {p.key: p.value for p in interpretants["golden-dawn-kabbalah"].target_sign.properties}
    assert peh_properties == {"alphabet_position": "17", "numeric_value": "80"}


def test_intersemiotic_target_interpretants_gather_its_own_manifestation_interpretants(
    store: KuzuGraphStore,
) -> None:
    """`target_interpretants` pulls in the target sign's own manifestation
    interpretants (across whichever tradition it's manifested under) — not
    just its bare `properties` — so retrieval query construction (FR-CO-03) can
    draw on what the target itself *means* (e.g. a Hebrew letter's Sepher
    Yetzirah foundation), not only intrinsic facts like its numeric value.
    Properties never appear here, at any scope — this is the concrete fix for
    the properties-asymmetry the retrieval pipeline used to have."""
    _seed_fixture(store)
    golden_dawn = Tradition(
        id="golden-dawn-kabbalah", slug="golden-dawn-kabbalah", name="Golden Dawn Kabbalah", domain="kabbalah"
    )
    peh_with_meaning = Sign(
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
    peh_manifestation = Manifestation(
        id="hebrew-letter-peh::golden-dawn-kabbalah",
        sign_id="hebrew-letter-peh",
        tradition=golden_dawn,
        display_name="Peh",
        interpretants=(Interpretant(id="peh-interp-meaning", type="meaning", value="Mouth"),),
        created_at=CREATED_AT,
    )
    store.upsert_sign_with_manifestation(peh_with_meaning, peh_manifestation)

    facts = store.get_manifestation("the-tower", "rider-waite")
    peh_interpretant = next(
        i for i in facts.sign.intersemiotic_interpretants if i.target_sign.slug == "hebrew-letter-peh"
    )

    assert {a.type: a.value for a in peh_interpretant.target_interpretants} == {"meaning": "Mouth"}
    # Peh's own properties are unaffected — the two stay on separate fields.
    assert {p.key for p in peh_interpretant.target_sign.properties} == {"alphabet_position", "numeric_value"}


def test_intersemiotic_target_with_zero_manifestations_is_valid(store: KuzuGraphStore) -> None:
    """A sign (Path: Tiphareth-Yesod) with no Manifestation at all must still be a
    valid INTERSEMIOTIC endpoint, now that the edge connects Sign -> Sign directly."""
    _seed_fixture(store)

    peh_facts = store.get_manifestation("hebrew-letter-peh", "golden-dawn-kabbalah")

    assert len(peh_facts.sign.intersemiotic_interpretants) == 1
    path_interpretant = peh_facts.sign.intersemiotic_interpretants[0]
    assert path_interpretant.target_sign.slug == "path-tiphareth-yesod"
    assert path_interpretant.target_sign.canonical_name == "Path: Tiphareth-Yesod"


def test_source_structure_scheme_round_trips(store: KuzuGraphStore) -> None:
    store.upsert_source(
        Source(
            id="en_drb",
            domain="scripture",
            title="Douay-Rheims Bible",
            author="English College at Douay",
            structure_scheme="scripture_verse",
        )
    )

    source = store.get_source("en_drb")

    assert source.structure_scheme == "scripture_verse"


def test_source_structure_scheme_defaults_to_empty(store: KuzuGraphStore) -> None:
    store.upsert_source(Source(id="waite", domain="tarot", title="T", author="A"))

    source = store.get_source("waite")

    assert source.structure_scheme == ""


def test_source_chapter_section_fields_round_trip(store: KuzuGraphStore) -> None:
    store.upsert_source(
        Source(
            id="en_goldenbough",
            domain="symbolism",
            title="The Golden Bough",
            author="Sir James George Frazer",
            structure_scheme="chapter_section",
            chapter_pattern=r"[IVXLCM]+\. [A-Z].+",
            subsection_pattern=r"\d+\. [A-Z].+",
            body_start_occurrence=15,
            body_end_occurrence=28,
        )
    )

    source = store.get_source("en_goldenbough")

    assert source.chapter_pattern == r"[IVXLCM]+\. [A-Z].+"
    assert source.subsection_pattern == r"\d+\. [A-Z].+"
    assert source.body_start_occurrence == 15
    assert source.body_end_occurrence == 28


def test_source_chapter_section_fields_default(store: KuzuGraphStore) -> None:
    store.upsert_source(Source(id="waite2", domain="tarot", title="T", author="A"))

    source = store.get_source("waite2")

    assert source.chapter_pattern == ""
    assert source.subsection_pattern == ""
    assert source.body_start_occurrence == 1
    assert source.body_end_occurrence == 0


def test_upserts_are_idempotent(store: KuzuGraphStore) -> None:
    _seed_fixture(store)
    _seed_fixture(store)  # re-run everything with identical data

    facts = store.get_manifestation("the-tower", "rider-waite")

    assert len(facts.manifestation.interpretants) == 1
    assert len(facts.manifestation.citations) == 1
    assert len(facts.sign.intersemiotic_interpretants) == 2

    peh_target = next(i for i in facts.sign.intersemiotic_interpretants if i.target_sign.slug == "hebrew-letter-peh")
    assert len(peh_target.target_sign.properties) == 2


def test_reupserting_with_a_renamed_manifestation_interpretant_type_leaves_no_stale_one(
    store: KuzuGraphStore,
) -> None:
    """An Interpretant's id is derived from its position (sign_loader.py), so a
    curator renaming its `type` in the YAML (e.g. `assignation` -> `planet`)
    must not leave the old interpretant node orphaned but still linked (a real
    bug found via a live query text unexpectedly containing both the old and
    new value)."""
    _seed_fixture(store)
    rider_waite = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")
    the_tower = Sign(
        id="the-tower",
        slug="the-tower",
        canonical_name="The Tower",
        sign_type="major-arcana",
        semiotic_system="tarot",
    )
    renamed_manifestation = Manifestation(
        id="the-tower::rider-waite",
        sign_id="the-tower",
        tradition=rider_waite,
        display_name="The Tower",
        denotation="Sudden upheaval; the collapse of false structures.",
        interpretants=(Interpretant(id="interp-primary-element", type="primary_element", value="Fire"),),
        created_at=CREATED_AT,
    )

    store.upsert_sign_with_manifestation(the_tower, renamed_manifestation)

    facts = store.get_manifestation("the-tower", "rider-waite")
    assert [i.type for i in facts.manifestation.interpretants] == ["primary_element"]


def test_reupserting_with_a_renamed_sign_property_key_leaves_no_stale_one(store: KuzuGraphStore) -> None:
    """Same reconciliation, for `Sign.properties` this time."""
    _seed_fixture(store)
    renamed_peh = Sign(
        id="hebrew-letter-peh",
        slug="hebrew-letter-peh",
        canonical_name="Peh",
        sign_type="hebrew-letter",
        semiotic_system="hebrew_alef_bet",
        properties=(Property(id="peh-prop-gematria", key="gematria_value", value="80"),),
    )

    store.upsert_sign(renamed_peh)

    facts = store.get_manifestation("the-tower", "rider-waite")
    peh = next(
        i for i in facts.sign.intersemiotic_interpretants if i.target_sign.slug == "hebrew-letter-peh"
    ).target_sign
    assert [p.key for p in peh.properties] == ["gematria_value"]


def test_sign_properties_are_distinct_from_manifestation_interpretants(store: KuzuGraphStore) -> None:
    """Intrinsic Sign.properties (HAS_PROPERTY from Sign) must not be conflated
    with tradition-scoped Manifestation.interpretants (HAS_INTERPRETANT from
    Manifestation), even though properties reuse the same node/rel table
    regardless of which node they attach to."""
    _seed_fixture(store)

    facts = store.get_manifestation("the-tower", "rider-waite")
    peh = next(
        i for i in facts.sign.intersemiotic_interpretants if i.target_sign.slug == "hebrew-letter-peh"
    ).target_sign

    assert {p.key for p in peh.properties} == {"alphabet_position", "numeric_value"}
    # the-tower's own manifestation-level interpretant ("element") must not leak onto Peh
    assert "element" not in {p.key for p in peh.properties}


def test_sign_not_found_raises(store: KuzuGraphStore) -> None:
    _seed_fixture(store)
    with pytest.raises(SignNotFoundError):
        store.get_manifestation("nonexistent-sign", "rider-waite")


def test_tradition_not_found_raises(store: KuzuGraphStore) -> None:
    _seed_fixture(store)
    with pytest.raises(TraditionNotFoundError):
        store.get_manifestation("the-tower", "nonexistent-tradition")


def test_manifestation_not_found_raises_when_sign_and_tradition_exist_but_unlinked(store: KuzuGraphStore) -> None:
    _seed_fixture(store)
    with pytest.raises(ManifestationNotFoundError):
        store.get_manifestation("the-tower", "golden-dawn-kabbalah")


def test_list_traditions_returns_every_tradition_sorted_by_slug(store: KuzuGraphStore) -> None:
    _seed_fixture(store)
    traditions = store.list_traditions()
    assert [t.slug for t in traditions] == ["golden-dawn-kabbalah", "pre-golden-dawn", "rider-waite"]


def test_list_signs_excludes_signs_with_zero_manifestations(store: KuzuGraphStore) -> None:
    _seed_fixture(store)
    summaries = {s.slug: s for s in store.list_signs()}
    assert "path-tiphareth-yesod" not in summaries
    assert set(summaries) == {"the-tower", "hebrew-letter-peh", "hebrew-letter-ayin"}


def test_list_signs_reports_every_tradition_a_sign_is_manifested_in(store: KuzuGraphStore) -> None:
    _seed_fixture(store)
    the_tower = next(s for s in store.list_signs() if s.slug == "the-tower")
    assert the_tower.canonical_name == "The Tower"
    assert the_tower.sign_type == "major-arcana"
    assert the_tower.semiotic_system == "tarot"
    assert the_tower.tradition_slugs == ("rider-waite",)


def test_list_semiotic_systems_returns_every_distinct_system_sorted(store: KuzuGraphStore) -> None:
    _seed_fixture(store)
    assert store.list_semiotic_systems() == ("hebrew_alef_bet", "tarot")


def test_list_semiotic_systems_excludes_a_system_whose_signs_have_no_manifestation(store: KuzuGraphStore) -> None:
    """Mirrors `list_signs`: a semiotic system offered here must actually
    lead somewhere — `path-tiphareth-yesod` (hebrew_alef_bet, zero
    manifestations) doesn't disqualify hebrew_alef_bet only because two
    *other* hebrew_alef_bet signs (Peh, Ayin) do have one; a system with
    *only* unmanifested signs must be excluded entirely."""
    dead_system = Sign(
        id="dead-sign",
        slug="dead-sign",
        canonical_name="Dead Sign",
        sign_type="unmanifested",
        semiotic_system="dead_system",
    )
    store.upsert_sign(dead_system)
    assert store.list_semiotic_systems() == ()
