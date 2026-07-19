"""Unit tests for the structured-data loader (T11): name resolution, referential
integrity validated before any write, and idempotent upserts against a real
KuzuGraphStore."""

from pathlib import Path

import pytest

from mythrix.core.errors import IngestValidationError, InterpretationNotFoundError, SymbolNotFoundError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.loaders.symbol_loader import load_directory

FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def store(tmp_path: Path) -> KuzuGraphStore:
    return KuzuGraphStore(tmp_path / "graph.kuzu")


def test_loads_the_worked_example_fixture_end_to_end(store: KuzuGraphStore) -> None:
    """Loads tarot/ and kabbalah/ together (mirrors spec.md's Fool/Samekh example,
    which spans two domains) and confirms every mechanism landed correctly."""
    load_directory(FIXTURES_ROOT, store)

    fool = store.get_interpretation("the-fool", "rider-waite")
    assert fool.interpretation.display_name == "The Fool"
    keyword_values = {a.value for a in fool.interpretation.attributes if a.key == "keyword"}
    assert keyword_values == {"dog", "white rose", "cliff"}
    assert len(fool.interpretation.citations) == 1
    assert fool.interpretation.citations[0].source.title == "The Pictorial Key to the Tarot"
    assert fool.interpretation.citations[0].locator == "p. 97"

    assert len(fool.symbol.relationships) == 1
    correspondence = fool.symbol.relationships[0]
    assert correspondence.target_symbol.slug == "samekh"
    assert correspondence.according_to_tradition.slug == "golden-dawn-kabbalah"

    samekh = store.get_interpretation("samekh", "golden-dawn-kabbalah")
    properties = {p.key: p.value for p in samekh.symbol.properties}
    assert properties == {"alphabet_position": "15", "numeric_value": "60"}
    assert len(samekh.symbol.relationships) == 3
    targets = {r.target_symbol.slug for r in samekh.symbol.relationships}
    assert targets == {"path-tiphareth-yesod", "tiphareth", "yesod"}

    # Bare correspondence targets (FR22) exist in the graph despite zero interpretations.
    with pytest.raises(InterpretationNotFoundError):
        store.get_interpretation("tiphareth", "golden-dawn-kabbalah")


def test_bare_correspondence_target_has_no_interpretation_but_exists(store: KuzuGraphStore) -> None:
    load_directory(FIXTURES_ROOT, store)

    yesod_relationship = next(
        r
        for r in store.get_interpretation("samekh", "golden-dawn-kabbalah").symbol.relationships
        if r.target_symbol.slug == "yesod"
    )
    assert yesod_relationship.target_symbol.canonical_name == "Yesod"


def test_loading_twice_is_idempotent(store: KuzuGraphStore) -> None:
    load_directory(FIXTURES_ROOT, store)
    load_directory(FIXTURES_ROOT, store)

    fool = store.get_interpretation("the-fool", "rider-waite")
    assert len(fool.symbol.relationships) == 1
    assert len({a.value for a in fool.interpretation.attributes if a.key == "keyword"}) == 3


def test_renaming_a_symbols_tradition_removes_the_stale_interpretation(tmp_path: Path, store: KuzuGraphStore) -> None:
    """An Interpretation's id is derived from its symbol *and* tradition slug,
    so a curator renaming a tradition changes every interpretation's own id
    under it (a real scenario this project hit: `sepher-yetzirah` renamed to
    `sepher-yetzirah-gra`) — the old Interpretation node, and its attributes,
    must not be left orphaned but still linked to the symbol."""
    _write_tradition(tmp_path, "old-trad", "Old Tradition", "kabbalah")
    (tmp_path / "symbols").mkdir(parents=True, exist_ok=True)
    (tmp_path / "symbols" / "aleph.yaml").write_text(
        """
symbol:
  name: "Aleph"
  type: hebrew-letter
interpretations:
  - tradition: old-trad
    display_name: "Aleph"
    attributes:
      - key: assignation
        value: Air
""",
        encoding="utf-8",
    )
    load_directory(tmp_path, store)

    (tmp_path / "traditions" / "old-trad.yaml").unlink()
    _write_tradition(tmp_path, "new-trad", "New Tradition", "kabbalah")
    (tmp_path / "symbols" / "aleph.yaml").write_text(
        """
symbol:
  name: "Aleph"
  type: hebrew-letter
interpretations:
  - tradition: new-trad
    display_name: "Aleph"
    attributes:
      - key: foundation
        value: Air
""",
        encoding="utf-8",
    )

    load_directory(tmp_path, store)

    facts = store.get_interpretation("aleph", "new-trad")
    assert [a.key for a in facts.interpretation.attributes] == ["foundation"]

    result = store._execute(
        "MATCH (:Symbol {id: $id})-[:HAS_INTERPRETATION]->(i:Interpretation) RETURN i.id", {"id": "aleph"}
    )
    interpretation_ids = []
    while result.has_next():
        interpretation_ids.append(result.get_next()[0])
    assert interpretation_ids == ["aleph::new-trad"]


def test_dangling_cites_reference_is_rejected_and_nothing_is_written(tmp_path: Path, store: KuzuGraphStore) -> None:
    _write_symbol_with_bad_cites(tmp_path)

    with pytest.raises(IngestValidationError):
        load_directory(tmp_path, store)

    with pytest.raises(SymbolNotFoundError):
        store.get_interpretation("the-fool", "rider-waite")


def test_unresolvable_corresponds_to_target_is_rejected(tmp_path: Path, store: KuzuGraphStore) -> None:
    _write_tradition(tmp_path, "rider-waite", "Rider-Waite-Smith", "tarot")
    (tmp_path / "symbols").mkdir(parents=True, exist_ok=True)
    (tmp_path / "symbols" / "the-fool.yaml").write_text(
        """
symbol:
  name: "The Fool"
  type: major-arcana
interpretations:
  - tradition: rider-waite
    display_name: "The Fool"
    corresponds_to:
      - to: "Nonexistent Symbol"
        relationship: hebrew_letter
        according_to: "Rider-Waite-Smith"
""",
        encoding="utf-8",
    )

    with pytest.raises(IngestValidationError, match="Unresolved symbol reference"):
        load_directory(tmp_path, store)


def test_ambiguous_tradition_reference_is_rejected(tmp_path: Path, store: KuzuGraphStore) -> None:
    _write_tradition(tmp_path, "golden-dawn-kabbalah", "Golden Dawn Kabbalah", "kabbalah")
    _write_tradition(tmp_path, "golden-dawn-tarot", "Golden Dawn Tarot", "tarot")
    (tmp_path / "symbols").mkdir(parents=True, exist_ok=True)
    (tmp_path / "symbols" / "samekh.yaml").write_text(
        """
symbol:
  name: "Samekh"
  type: hebrew-letter
interpretations:
  - tradition: golden-dawn-kabbalah
    display_name: "Samekh"
    corresponds_to:
      - to: "Samekh"
        relationship: self_reference
        according_to: "Golden Dawn"
""",
        encoding="utf-8",
    )

    with pytest.raises(IngestValidationError, match="Ambiguous tradition reference"):
        load_directory(tmp_path, store)


def _write_tradition(root: Path, slug: str, name: str, domain: str) -> None:
    directory = root / "traditions"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.yaml").write_text(f'tradition:\n  name: "{name}"\n  domain: {domain}\n', encoding="utf-8")


def _write_symbol_with_bad_cites(root: Path) -> None:
    _write_tradition(root, "rider-waite", "Rider-Waite-Smith", "tarot")
    (root / "symbols").mkdir(parents=True, exist_ok=True)
    (root / "symbols" / "the-fool.yaml").write_text(
        """
symbol:
  name: "The Fool"
  type: major-arcana
interpretations:
  - tradition: rider-waite
    display_name: "The Fool"
    cites: "Some Nonexistent Source, p. 1"
""",
        encoding="utf-8",
    )
