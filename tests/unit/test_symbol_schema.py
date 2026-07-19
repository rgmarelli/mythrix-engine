"""Unit tests for the structured-data authoring format's pydantic models (T10)."""

import pytest
import yaml
from pydantic import ValidationError

from mythrix.core.loaders.symbol_schema import SourceFile, SymbolFile, TraditionFile

THE_FOOL_YAML = """
symbol:
  name: "The Fool"
  type: major-arcana

interpretations:
  - tradition: rider-waite
    display_name: "The Fool"
    summary: "A man dressed in ragged, colorful jester-like clothes."
    keywords: [dog, white rose, cliff]
    cites: "Waite, Pictorial Key to the Tarot, p. 97"
    corresponds_to:
      - to: "Samekh"
        relationship: hebrew_letter
        according_to: "Golden Dawn"
"""

SAMEKH_YAML = """
symbol:
  name: "Samekh"
  type: hebrew-letter
  properties:
    - {key: alphabet_position, value: "15"}
    - {key: numeric_value, value: "60"}

interpretations:
  - tradition: golden-dawn-kabbalah
    display_name: "Samekh (ס)"
    summary: "Support and protection; the serpent encircling the initiate."
    corresponds_to:
      - to: "Path: Tiphareth-Yesod"
        relationship: tree_of_life_path
        according_to: "Golden Dawn"
      - to: "Tiphareth"
        relationship: sephirah
        according_to: "Golden Dawn"
"""

BARE_SYMBOL_YAML = """
symbol:
  name: "Tiphareth"
  type: sephirah
"""


def test_parses_the_fool_worked_example() -> None:
    parsed = SymbolFile.model_validate(yaml.safe_load(THE_FOOL_YAML))

    assert parsed.symbol.name == "The Fool"
    assert parsed.symbol.type == "major-arcana"
    assert len(parsed.interpretations) == 1

    interpretation = parsed.interpretations[0]
    assert interpretation.keywords == ("dog", "white rose", "cliff")
    assert interpretation.cites == ("Waite, Pictorial Key to the Tarot, p. 97",)
    assert len(interpretation.corresponds_to) == 1
    assert interpretation.corresponds_to[0].to == "Samekh"
    assert interpretation.corresponds_to[0].according_to == "Golden Dawn"


def test_parses_samekh_worked_example_with_properties_and_multiple_correspondences() -> None:
    parsed = SymbolFile.model_validate(yaml.safe_load(SAMEKH_YAML))

    assert {p.key: p.value for p in parsed.symbol.properties} == {"alphabet_position": "15", "numeric_value": "60"}
    assert len(parsed.interpretations[0].corresponds_to) == 2


def test_bare_symbol_with_no_interpretations_is_valid() -> None:
    """FR22: a symbol file may omit `interpretations` entirely."""
    parsed = SymbolFile.model_validate(yaml.safe_load(BARE_SYMBOL_YAML))

    assert parsed.symbol.name == "Tiphareth"
    assert parsed.interpretations == ()


def test_malformed_symbol_file_missing_required_field_raises() -> None:
    malformed = {"symbol": {"name": "The Fool"}}  # missing required `type`

    with pytest.raises(ValidationError):
        SymbolFile.model_validate(malformed)


def test_unknown_field_is_rejected() -> None:
    """extra="forbid" catches curator typos rather than silently ignoring them."""
    malformed = {"symbol": {"name": "The Fool", "type": "major-arcana", "typo_field": "oops"}}

    with pytest.raises(ValidationError):
        SymbolFile.model_validate(malformed)


def test_parses_tradition_file() -> None:
    parsed = TraditionFile.model_validate(
        {"tradition": {"name": "Rider-Waite-Smith", "domain": "tarot", "description": "1909 deck"}}
    )
    assert parsed.tradition.name == "Rider-Waite-Smith"


def test_parses_source_file() -> None:
    parsed = SourceFile.model_validate(
        {"source": {"title": "The Pictorial Key to the Tarot", "author": "A. E. Waite", "publication_year": 1910}}
    )
    assert parsed.source.author == "A. E. Waite"
