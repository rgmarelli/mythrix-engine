"""Unit tests for the structured-data loader (T11): name resolution, referential
integrity validated before any write, and idempotent upserts against a real
KuzuGraphStore."""

from pathlib import Path

import pytest

from mythrix.core.errors import IngestValidationError, ManifestationNotFoundError, SignNotFoundError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.loaders.sign_loader import load_directory

FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def store(tmp_path: Path) -> KuzuGraphStore:
    return KuzuGraphStore(tmp_path / "graph.kuzu")


def test_loads_the_worked_example_fixture_end_to_end(store: KuzuGraphStore) -> None:
    """Loads tarot/ and kabbalah/ together (mirrors spec.md's Fool/Samekh example,
    which spans two domains) and confirms every mechanism landed correctly."""
    load_directory(FIXTURES_ROOT, store)

    fool = store.get_manifestation("the-fool", "rider-waite")
    assert fool.manifestation.display_name == "The Fool"
    concept_values = {i.value for i in fool.manifestation.interpretants if i.type == "concept"}
    assert concept_values == {"dog", "white rose", "cliff"}
    assert len(fool.manifestation.citations) == 1
    assert fool.manifestation.citations[0].source.title == "The Pictorial Key to the Tarot"
    assert fool.manifestation.citations[0].locator == "p. 97"

    assert len(fool.sign.intersemiotic_interpretants) == 1
    interpretant = fool.sign.intersemiotic_interpretants[0]
    assert interpretant.target_sign.slug == "samekh"
    assert interpretant.according_to.slug == "golden-dawn-kabbalah"

    samekh = store.get_manifestation("samekh", "golden-dawn-kabbalah")
    interpretant_values = {i.type: i.value for i in samekh.manifestation.interpretants}
    assert interpretant_values == {"alphabet_position": "15", "numeric_value": "60"}
    assert len(samekh.sign.intersemiotic_interpretants) == 3
    targets = {i.target_sign.slug for i in samekh.sign.intersemiotic_interpretants}
    assert targets == {"path-tiphareth-yesod", "tiphareth", "yesod"}

    # Bare correspondence targets (FR-DM-05) exist in the graph despite zero manifestations.
    with pytest.raises(ManifestationNotFoundError):
        store.get_manifestation("tiphareth", "golden-dawn-kabbalah")


def test_bare_correspondence_target_has_no_manifestation_but_exists(store: KuzuGraphStore) -> None:
    load_directory(FIXTURES_ROOT, store)

    yesod_interpretant = next(
        i
        for i in store.get_manifestation("samekh", "golden-dawn-kabbalah").sign.intersemiotic_interpretants
        if i.target_sign.slug == "yesod"
    )
    assert yesod_interpretant.target_sign.canonical_name == "Yesod"


def test_loading_twice_is_idempotent(store: KuzuGraphStore) -> None:
    load_directory(FIXTURES_ROOT, store)
    load_directory(FIXTURES_ROOT, store)

    fool = store.get_manifestation("the-fool", "rider-waite")
    assert len(fool.sign.intersemiotic_interpretants) == 1
    assert len({i.value for i in fool.manifestation.interpretants if i.type == "concept"}) == 3


def test_renaming_a_signs_tradition_removes_the_stale_manifestation(tmp_path: Path, store: KuzuGraphStore) -> None:
    """A Manifestation's id is derived from its sign *and* tradition slug, so a
    curator renaming a tradition changes every manifestation's own id under it
    (a real scenario this project hit: `sepher-yetzirah` renamed to
    `sepher-yetzirah-gra`) — the old Manifestation node, and its interpretants,
    must not be left orphaned but still linked to the sign."""
    _write_tradition(tmp_path, "old-trad", "Old Tradition", "kabbalah")
    (tmp_path / "signs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "signs" / "aleph.yaml").write_text(
        """
semiotic_system: hebrew_alef_bet
sign:
  name: "Aleph"
  type: hebrew-letter
  manifestations:
    - tradition: old-trad
      display_name: "Aleph"
      interpretants:
        - {type: assignation, value: Air}
""",
        encoding="utf-8",
    )
    load_directory(tmp_path, store)

    (tmp_path / "traditions" / "old-trad.yaml").unlink()
    _write_tradition(tmp_path, "new-trad", "New Tradition", "kabbalah")
    (tmp_path / "signs" / "aleph.yaml").write_text(
        """
semiotic_system: hebrew_alef_bet
sign:
  name: "Aleph"
  type: hebrew-letter
  manifestations:
    - tradition: new-trad
      display_name: "Aleph"
      interpretants:
        - {type: foundation, value: Air}
""",
        encoding="utf-8",
    )

    load_directory(tmp_path, store)

    facts = store.get_manifestation("aleph", "new-trad")
    assert [i.type for i in facts.manifestation.interpretants] == ["foundation"]

    result = store._execute(
        "MATCH (:Sign {id: $id})-[:HAS_MANIFESTATION]->(m:Manifestation) RETURN m.id", {"id": "aleph"}
    )
    manifestation_ids = []
    while result.has_next():
        manifestation_ids.append(result.get_next()[0])
    assert manifestation_ids == ["aleph::new-trad"]


def test_dangling_cites_reference_is_rejected_and_nothing_is_written(tmp_path: Path, store: KuzuGraphStore) -> None:
    _write_sign_with_bad_cites(tmp_path)

    with pytest.raises(IngestValidationError):
        load_directory(tmp_path, store)

    with pytest.raises(SignNotFoundError):
        store.get_manifestation("the-fool", "rider-waite")


def test_unresolvable_intersemiotic_target_is_rejected(tmp_path: Path, store: KuzuGraphStore) -> None:
    _write_tradition(tmp_path, "rider-waite", "Rider-Waite-Smith", "tarot")
    (tmp_path / "signs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "signs" / "the-fool.yaml").write_text(
        """
semiotic_system: tarot_cards
sign:
  name: "The Fool"
  type: major-arcana
  manifestations:
    - tradition: rider-waite
      display_name: "The Fool"
      intersemiotic_interpretants:
        - target_system: hebrew_alef_bet
          target_sign: "Nonexistent Sign"
          relationship: hebrew_letter
          according_to: "Rider-Waite-Smith"
""",
        encoding="utf-8",
    )

    with pytest.raises(IngestValidationError, match="No sign found in semiotic system"):
        load_directory(tmp_path, store)


def test_ambiguous_tradition_reference_is_rejected(tmp_path: Path, store: KuzuGraphStore) -> None:
    _write_tradition(tmp_path, "golden-dawn-kabbalah", "Golden Dawn Kabbalah", "kabbalah")
    _write_tradition(tmp_path, "golden-dawn-tarot", "Golden Dawn Tarot", "tarot")
    (tmp_path / "signs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "signs" / "samekh.yaml").write_text(
        """
semiotic_system: hebrew_alef_bet
sign:
  name: "Samekh"
  type: hebrew-letter
  manifestations:
    - tradition: golden-dawn-kabbalah
      display_name: "Samekh"
      intersemiotic_interpretants:
        - target_system: hebrew_alef_bet
          target_sign: "Samekh"
          relationship: self_reference
          according_to: "Golden Dawn"
""",
        encoding="utf-8",
    )

    with pytest.raises(IngestValidationError, match="Ambiguous tradition reference"):
        load_directory(tmp_path, store)


def test_target_system_scopes_resolution_between_two_signs_of_the_same_name(
    tmp_path: Path, store: KuzuGraphStore
) -> None:
    """Two signs named "The Sun" in different semiotic systems must not be
    ambiguous with each other — `target_system` narrows resolution to the
    named system before the tiered name-matching tiers ever run."""
    _write_tradition(tmp_path, "rider-waite", "Rider-Waite-Smith", "tarot")
    _write_tradition(tmp_path, "some-astrology", "Some Astrology System", "astrology")
    (tmp_path / "signs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "signs" / "the-sun-tarot.yaml").write_text(
        """
semiotic_system: tarot_cards
sign:
  name: "The Sun"
  type: major-arcana
""",
        encoding="utf-8",
    )
    (tmp_path / "signs" / "the-sun-astrology.yaml").write_text(
        """
semiotic_system: astrology
sign:
  name: "The Sun"
  type: planet
""",
        encoding="utf-8",
    )
    (tmp_path / "signs" / "the-fool.yaml").write_text(
        """
semiotic_system: tarot_cards
sign:
  name: "The Fool"
  type: major-arcana
  manifestations:
    - tradition: rider-waite
      display_name: "The Fool"
      intersemiotic_interpretants:
        - target_system: astrology
          target_sign: "The Sun"
          relationship: planetary_correspondence
          according_to: "Some Astrology System"
""",
        encoding="utf-8",
    )

    load_directory(tmp_path, store)

    fool = store.get_manifestation("the-fool", "rider-waite")
    assert len(fool.sign.intersemiotic_interpretants) == 1
    assert fool.sign.intersemiotic_interpretants[0].target_sign.slug == "the-sun-astrology"


def _write_tradition(root: Path, slug: str, name: str, domain: str) -> None:
    directory = root / "traditions"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.yaml").write_text(f'tradition:\n  name: "{name}"\n  domain: {domain}\n', encoding="utf-8")


def _write_sign_with_bad_cites(root: Path) -> None:
    _write_tradition(root, "rider-waite", "Rider-Waite-Smith", "tarot")
    (root / "signs").mkdir(parents=True, exist_ok=True)
    (root / "signs" / "the-fool.yaml").write_text(
        """
semiotic_system: tarot_cards
sign:
  name: "The Fool"
  type: major-arcana
  manifestations:
    - tradition: rider-waite
      display_name: "The Fool"
      cites: "Some Nonexistent Source, p. 1"
""",
        encoding="utf-8",
    )
