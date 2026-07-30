# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the structured-data authoring format's pydantic models (T10)."""

import pytest
import yaml
from pydantic import ValidationError

from mythrix.core.loaders.sign_schema import InterpretantEntry, PropertyEntry, SignFile, SourceFile, TraditionFile

THE_FOOL_YAML = """
semiotic_system: tarot_cards
sign:
  name: "The Fool"
  type: major-arcana

  manifestations:
    - tradition: rider-waite
      display_name: "The Fool"
      denotation: "A man dressed in ragged, colorful jester-like clothes."
      interpretants:
        - {type: concept, value: dog}
        - {type: concept, value: white rose}
        - {type: concept, value: cliff}
      cites: "Waite, Pictorial Key to the Tarot, p. 97"
      intersemiotic_interpretants:
        - target_system: hebrew_alef_bet
          target_sign: "Samekh"
          relationship: hebrew_letter
          according_to: "Golden Dawn"
"""

SAMEKH_YAML = """
semiotic_system: hebrew_alef_bet
sign:
  name: "Samekh"
  type: hebrew-letter
  properties:
    - {key: alphabet_position, value: "15"}
    - {key: numeric_value, value: "60"}

  manifestations:
    - tradition: golden-dawn-kabbalah
      display_name: "Samekh (ס)"
      denotation: "Support and protection; the serpent encircling the initiate."
      intersemiotic_interpretants:
        - target_system: hebrew_alef_bet
          target_sign: "Path: Tiphareth-Yesod"
          relationship: tree_of_life_path
          according_to: "Golden Dawn"
        - target_system: hebrew_alef_bet
          target_sign: "Tiphareth"
          relationship: sephirah
          according_to: "Golden Dawn"
"""

BARE_SIGN_YAML = """
semiotic_system: hebrew_alef_bet
sign:
  name: "Tiphareth"
  type: sephirah
"""


def test_parses_the_fool_worked_example() -> None:
    parsed = SignFile.model_validate(yaml.safe_load(THE_FOOL_YAML))

    assert parsed.semiotic_system == "tarot_cards"
    assert parsed.sign.name == "The Fool"
    assert parsed.sign.type == "major-arcana"
    assert len(parsed.sign.manifestations) == 1

    manifestation = parsed.sign.manifestations[0]
    assert [i.value for i in manifestation.interpretants] == ["dog", "white rose", "cliff"]
    assert manifestation.cites == ("Waite, Pictorial Key to the Tarot, p. 97",)
    assert len(manifestation.intersemiotic_interpretants) == 1
    assert manifestation.intersemiotic_interpretants[0].target_system == "hebrew_alef_bet"
    assert manifestation.intersemiotic_interpretants[0].target_sign == "Samekh"
    assert manifestation.intersemiotic_interpretants[0].according_to == "Golden Dawn"


def test_parses_samekh_worked_example_with_properties_and_multiple_intersemiotic_interpretants() -> None:
    parsed = SignFile.model_validate(yaml.safe_load(SAMEKH_YAML))

    assert {p.key: p.value for p in parsed.sign.properties} == {"alphabet_position": "15", "numeric_value": "60"}
    assert len(parsed.sign.manifestations[0].intersemiotic_interpretants) == 2


def test_property_value_as_a_yaml_list_is_joined_to_the_same_comma_separated_string() -> None:
    """A multi-concept value (e.g. a Hebrew letter's `meaning`) is a vector of
    atomic concepts either way — authoring it as `value: [Ox, teaching, master]`
    must normalize to the exact same internal string a hand-punctuated
    `value: "Ox, teaching, master"` would, since that's what
    `retrieval.pipeline._atomic_values` splits on."""
    from_list = PropertyEntry.model_validate({"key": "meaning", "value": ["Ox", "teaching", "master"]})
    from_string = PropertyEntry.model_validate({"key": "meaning", "value": "Ox, teaching, master"})

    assert from_list.value == from_string.value == "Ox, teaching, master"


def test_property_value_as_a_single_item_list_has_no_trailing_artifacts() -> None:
    parsed = PropertyEntry.model_validate({"key": "meaning", "value": ["laughter"]})

    assert parsed.value == "laughter"


def test_property_value_as_a_bare_yaml_number_is_coerced_to_its_string_form() -> None:
    """`Property`/`Interpretant.value` is always `str` internally — a curator
    authoring a gematria value or a deck position needn't quote it
    (`value: "9"`); a bare `value: 9` normalizes to the same string a quoted
    one would."""
    from_int = PropertyEntry.model_validate({"key": "numeric_value", "value": 9})
    from_string = PropertyEntry.model_validate({"key": "numeric_value", "value": "9"})

    assert from_int.value == from_string.value == "9"


def test_interpretant_value_as_a_bare_yaml_number_is_coerced_to_its_string_form() -> None:
    parsed = InterpretantEntry.model_validate({"type": "numeric_value", "value": 100})

    assert parsed.value == "100"


def test_property_value_as_a_bare_yaml_boolean_is_rejected() -> None:
    """A `bool` is a Python `int` subclass, but YAML's `yes`/`no`/`true`/`false`
    literals are a well-known authoring footgun — silently stringifying one to
    "True"/"False" would mask a curator's typo rather than surface it, so an
    unquoted boolean-looking value still fails validation."""
    with pytest.raises(ValidationError):
        PropertyEntry.model_validate({"key": "flag", "value": True})


def test_bare_sign_with_no_manifestations_is_valid() -> None:
    """FR-DM-05: a sign file may omit `manifestations` entirely."""
    parsed = SignFile.model_validate(yaml.safe_load(BARE_SIGN_YAML))

    assert parsed.sign.name == "Tiphareth"
    assert parsed.sign.manifestations == ()


def test_sign_id_is_accepted_but_not_required() -> None:
    """`docs/newmodel.yaml`'s worked example authors an explicit `sign.id` —
    accepted for shape compatibility, but the loader never reads it (a sign's
    real id/slug is always its file's stem)."""
    parsed = SignFile.model_validate(
        {"semiotic_system": "tarot_cards", "sign": {"id": "arcana_19", "name": "The Sun", "type": "major-arcana"}}
    )
    assert parsed.sign.id == "arcana_19"
    assert parsed.sign.name == "The Sun"


def test_malformed_sign_file_missing_required_field_raises() -> None:
    malformed = {"semiotic_system": "tarot_cards", "sign": {"name": "The Fool"}}  # missing required `type`

    with pytest.raises(ValidationError):
        SignFile.model_validate(malformed)


def test_missing_semiotic_system_is_rejected() -> None:
    malformed = {"sign": {"name": "The Fool", "type": "major-arcana"}}

    with pytest.raises(ValidationError):
        SignFile.model_validate(malformed)


def test_intersemiotic_interpretant_missing_target_system_is_rejected() -> None:
    malformed = {
        "semiotic_system": "tarot_cards",
        "sign": {
            "name": "The Fool",
            "type": "major-arcana",
            "manifestations": [
                {
                    "tradition": "rider-waite",
                    "display_name": "The Fool",
                    "intersemiotic_interpretants": [
                        {"target_sign": "Samekh", "relationship": "hebrew_letter", "according_to": "Golden Dawn"}
                    ],
                }
            ],
        },
    }

    with pytest.raises(ValidationError):
        SignFile.model_validate(malformed)


def test_unknown_field_is_rejected() -> None:
    """extra="forbid" catches curator typos rather than silently ignoring them."""
    malformed = {
        "semiotic_system": "tarot_cards",
        "sign": {"name": "The Fool", "type": "major-arcana", "typo_field": "oops"},
    }

    with pytest.raises(ValidationError):
        SignFile.model_validate(malformed)


def test_parses_tradition_file() -> None:
    parsed = TraditionFile.model_validate(
        {"tradition": {"name": "Rider-Waite-Smith", "domain": "tarot", "description": "1909 deck"}}
    )
    assert parsed.tradition.name == "Rider-Waite-Smith"


def test_parses_source_file() -> None:
    parsed = SourceFile.model_validate(
        {
            "source": {
                "id": "waite-pictorial-key",
                "domain": "tarot",
                "title": "The Pictorial Key to the Tarot",
                "author": "A. E. Waite",
                "publication_year": 1910,
            }
        }
    )
    assert parsed.source.author == "A. E. Waite"


def test_source_file_requires_id_and_domain() -> None:
    with pytest.raises(ValidationError):
        SourceFile.model_validate({"source": {"title": "The Pictorial Key to the Tarot", "author": "A. E. Waite"}})


def test_parses_chapter_section_structure_fields() -> None:
    parsed = SourceFile.model_validate(
        {
            "source": {
                "id": "en_goldenbough",
                "domain": "symbolism",
                "title": "The Golden Bough",
                "author": "Sir James George Frazer",
                "structure": {
                    "scheme": "chapter_section",
                    "chapter_pattern": r"[IVXLCM]+\. [A-Z].+",
                    "subsection_pattern": r"\d+\. [A-Z].+",
                    "body_start_occurrence": 15,
                    "body_end_occurrence": 28,
                },
            }
        }
    )
    structure = parsed.source.structure
    assert structure is not None
    assert structure.chapter_pattern == r"[IVXLCM]+\. [A-Z].+"
    assert structure.subsection_pattern == r"\d+\. [A-Z].+"
    assert structure.body_start_occurrence == 15
    assert structure.body_end_occurrence == 28


def test_chapter_section_structure_fields_default_when_unset() -> None:
    parsed = SourceFile.model_validate(
        {
            "source": {
                "id": "en_drb",
                "domain": "scripture",
                "title": "Douay-Rheims",
                "author": "English College at Douay & Rheims",
                "structure": {"scheme": "scripture_verse"},
            }
        }
    )
    structure = parsed.source.structure
    assert structure is not None
    assert structure.chapter_pattern is None
    assert structure.subsection_pattern is None
    assert structure.body_start_occurrence == 1
    assert structure.body_end_occurrence == 0
