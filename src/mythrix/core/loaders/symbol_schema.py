"""Pydantic models mirroring the human-authored YAML structured-data format
(spec.md "Structured-data authoring format", plan.md "Structured-data YAML format").

These models validate *shape* only (FR4's schema-validation half). Referential
integrity (does a named tradition/source/symbol actually exist) is `symbol_loader.py`'s
job, since it requires cross-file context these per-file models don't have.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class LoaderModel(BaseModel):
    """Base for authoring-format models: strict shape, but not frozen — these are
    transient parse results, immediately consumed by the loader and discarded."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TraditionBlock(LoaderModel):
    name: str
    domain: str
    description: str = ""


class TraditionFile(LoaderModel):
    """`data/<domain>/traditions/<slug>.yaml` — the filename stem is the slug."""

    tradition: TraditionBlock


class SourceBlock(LoaderModel):
    title: str
    author: str
    publication_year: int | None = None
    license: str = ""
    uri: str = ""


class SourceFile(LoaderModel):
    """`data/<domain>/sources/<slug>.yaml` — the filename stem is the slug."""

    source: SourceBlock


class PropertyEntry(LoaderModel):
    """One `properties:` or `attributes:` list entry.

    `retrievable: false` opts a fact out of retrieval query construction (FR8) —
    e.g. a tarot card's own `number` (its position in the deck), which is purely
    identifying and would only inject a stray token into a similarity search.
    Default `True`: most curated facts (including numeric ones with real symbolic
    weight, like a Hebrew letter's gematria value) belong in retrieval by default.
    """

    key: str
    value: str
    value_type: str = "string"
    retrievable: bool = True

    @field_validator("value", mode="before")
    @classmethod
    def _join_list_value(cls, value: object) -> object:
        """A value listing several distinct concepts under one key (e.g. a
        Hebrew letter's `meaning`, "Ox, teaching, master") is a vector of
        atomic concepts, not one phrase — `retrieval.pipeline._atomic_values`
        already treats it that way, splitting a comma-separated string back
        into one query per concept. Authoring it as a punctuated string is
        just an artifact of `Attribute.value` being a plain `str`; a curator
        may write the more honest `value: [Ox, teaching, master]` instead,
        normalized to the same internal comma-joined string right here so no
        downstream consumer (the graph schema, the retrieval pipeline) needs
        to learn a second representation."""
        return ", ".join(str(item) for item in value) if isinstance(value, list) else value


class CorrespondsToEntry(LoaderModel):
    """One inline correspondence (FR19) — `to`/`according_to` are human-readable
    names resolved against already-parsed symbols/traditions by the loader (FR18)."""

    to: str
    relationship: str
    according_to: str
    description: str = ""
    symmetric: bool = False
    confidence: str = "attributed"


class InterpretationEntry(LoaderModel):
    """One `interpretations:` list entry (FR2). `tradition` names a `Tradition` by
    slug or name (FR18); `cites` is a free-text citation resolved against loaded
    sources (see `symbol_loader._resolve_citation`)."""

    tradition: str
    display_name: str
    summary: str = ""
    keywords: tuple[str, ...] = ()
    cites: tuple[str, ...] = ()
    attributes: tuple[PropertyEntry, ...] = ()
    corresponds_to: tuple[CorrespondsToEntry, ...] = ()

    @field_validator("cites", mode="before")
    @classmethod
    def _coerce_single_cites_to_tuple(cls, value: object) -> object:
        """`cites: "..."` (a single string) is sugar for a one-element list —
        matches the worked example in spec.md, which shows the common case of a
        single citation without requiring a curator to wrap it in `[...]`."""
        return (value,) if isinstance(value, str) else value


class SymbolBlock(LoaderModel):
    name: str
    type: str
    notes: str = ""
    properties: tuple[PropertyEntry, ...] = ()


class SymbolFile(LoaderModel):
    """`data/<domain>/symbols/<slug>.yaml` — the filename stem is the slug.
    `interpretations` is entirely optional (FR22) — a symbol may exist purely as a
    correspondence target/anchor."""

    symbol: SymbolBlock
    interpretations: tuple[InterpretationEntry, ...] = ()
