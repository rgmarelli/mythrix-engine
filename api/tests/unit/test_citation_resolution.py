# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `_resolve_citation`'s "Author, Title[, Locator]" parsing —
regression coverage for a bug found while authoring the real T24 dataset: a
locator containing its own comma (e.g. "Part II, XVI. The Tower") was
misparsed by a naive "split on the last comma" rule."""

from pathlib import Path

import pytest

from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.loaders.sign_loader import load_directory


@pytest.fixture
def store(tmp_path: Path) -> KuzuGraphStore:
    return KuzuGraphStore(tmp_path / "graph.kuzu")


def _load_with_cites(tmp_path: Path, store: KuzuGraphStore, cites: str) -> None:
    (tmp_path / "traditions").mkdir(parents=True, exist_ok=True)
    (tmp_path / "traditions" / "rider-waite.yaml").write_text(
        'tradition:\n  name: "Rider-Waite-Smith"\n  domain: tarot\n', encoding="utf-8"
    )
    (tmp_path / "sources").mkdir(parents=True, exist_ok=True)
    (tmp_path / "sources" / "waite-pictorial-key.yaml").write_text(
        'source:\n  id: "waite-pictorial-key"\n  domain: tarot\n'
        '  title: "The Pictorial Key to the Tarot"\n  author: "Arthur Edward Waite"\n',
        encoding="utf-8",
    )
    (tmp_path / "signs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "signs" / "the-tower.yaml").write_text(
        f"""
semiotic_system: tarot
sign:
  name: "The Tower"
  type: major-arcana
  manifestations:
    - tradition: rider-waite
      display_name: "The Tower"
      cites: "{cites}"
""",
        encoding="utf-8",
    )
    load_directory(tmp_path, store)


def test_locator_containing_its_own_comma_is_preserved_verbatim(tmp_path: Path, store: KuzuGraphStore) -> None:
    _load_with_cites(
        tmp_path, store, "Waite, Pictorial Key to the Tarot, Part II: The Doctrine Behind the Veil, XVI. The Tower"
    )

    facts = store.get_manifestation("the-tower", "rider-waite")

    assert len(facts.manifestation.citations) == 1
    citation = facts.manifestation.citations[0]
    assert citation.source.title == "The Pictorial Key to the Tarot"
    assert citation.locator == "Part II: The Doctrine Behind the Veil, XVI. The Tower"


def test_citation_with_no_locator_resolves_with_empty_locator(tmp_path: Path, store: KuzuGraphStore) -> None:
    """A bare "Author, Title" citation (one comma, no locator) must not have
    the title mistaken for a locator."""
    _load_with_cites(tmp_path, store, "Waite, Pictorial Key to the Tarot")

    facts = store.get_manifestation("the-tower", "rider-waite")

    citation = facts.manifestation.citations[0]
    assert citation.source.title == "The Pictorial Key to the Tarot"
    assert citation.locator == ""


def test_simple_two_comma_citation_still_works_as_before(tmp_path: Path, store: KuzuGraphStore) -> None:
    _load_with_cites(tmp_path, store, "Waite, Pictorial Key to the Tarot, p. 97")

    facts = store.get_manifestation("the-tower", "rider-waite")

    citation = facts.manifestation.citations[0]
    assert citation.locator == "p. 97"
