"""Pydantic models mirroring the human-authored YAML structured-data format
(`specs/domain/structured-data.md`).

These models validate *shape* only (FR-SD-01's schema-validation half). Referential
integrity (does a named tradition/source/sign actually exist) is `sign_loader.py`'s
job, since it requires cross-file context these per-file models don't have.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class LoaderModel(BaseModel):
    """Base for authoring-format models: strict shape, but not frozen — these are
    transient parse results, immediately consumed by the loader and discarded."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _normalize_authored_value(value: object) -> object:
    """Shared `value`-field normalization for `PropertyEntry`/`InterpretantEntry`.

    A YAML list (e.g. a Hebrew letter's `meaning`, `[Ox, teaching, master]`) is
    a vector of atomic facts under one key/type, not one phrase — joined here
    into the same comma-separated string a curator could have hand-punctuated,
    so no downstream consumer needs to learn a second representation.

    A bare YAML number (e.g. a gematria value, `value: 9`) is coerced to its
    string form here rather than requiring a curator to quote it (`value:
    "9"`) — `Property`/`Interpretant.value` is always `str` internally (it
    feeds retrieval query text and `query.as_token` matching, both string
    operations), so there is nothing lost by accepting the more natural
    unquoted form. `bool` is deliberately excluded even though it is a `int`
    subclass in Python: YAML's `yes`/`no`/`true`/`false`/`on`/`off` literals
    are a well-known footgun, and silently stringifying `True`/`False` would
    mask a curator's typo rather than surface it — an unquoted boolean-looking
    value still fails validation, prompting the curator to quote it.
    """
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if not isinstance(value, bool) and isinstance(value, int | float):
        return str(value)
    return value


class TraditionBlock(LoaderModel):
    name: str
    domain: str
    description: str = ""


class TraditionFile(LoaderModel):
    """`data/<domain>/traditions/<slug>.yaml` — the filename stem is the slug."""

    tradition: TraditionBlock


class StructureBlock(LoaderModel):
    """A corpus source's `structure:` block (FR-CO-05): names the structural segmenter (`mythrix.core.vector.segmentation`)
    that turns this source's raw text into segments along its own declared
    structure, rather than a fixed word-count chunk."""

    scheme: str


class SourceBlock(LoaderModel):
    """`id` is always authored explicitly here — not derived from the YAML
    file's own name, since a corpus source's file is named descriptively
    (`douay-rheims-bible.yaml`) while its `id` is a short reference key
    (`en_drb`). `domain` names the broad subject area this source belongs to
    (the same free-text vocabulary `Tradition.domain` uses, e.g. "tarot",
    "scripture") — required, since it is what a corpus chunk is tagged with
    in place of a tradition (FR-CO-02). `citation_label` is only meaningful for a
    source that gets ingested into the document corpus; left empty for one
    that's only ever cited via a `Citation`. `structure` is optional — a
    source that doesn't declare one falls back to fixed word-count chunking
    (FR-CO-05)."""

    id: str
    domain: str
    citation_label: str = ""
    title: str
    author: str
    publication_year: int | None = None
    license: str = ""
    uri: str = ""
    description: str = ""
    structure: StructureBlock | None = None


class SourceFile(LoaderModel):
    """`data/semiotic_systems/<system>/sources/*.yaml` (a source citable by a
    sign's own manifestations) or `data/corpus/<domain>/<source-id>/*.yaml`
    (a source ingested into the document corpus, colocated with its raw
    text) — either way, `source.id` names the entity, not the file's own
    name or location."""

    source: SourceBlock


class PropertyEntry(LoaderModel):
    """One `properties:` list entry, at either sign or manifestation scope.

    A property is never used to build retrieval query text (FR-CO-03, FR-DM-04) —
    unlike an `InterpretantEntry`, there is no opt-out flag here, since
    eligibility is decided by which list (`properties:` vs `interpretants:`)
    an entry appears in, not by a per-entry setting.
    """

    key: str
    value: str

    @field_validator("value", mode="before")
    @classmethod
    def _normalize_value(cls, value: object) -> object:
        return _normalize_authored_value(value)


class QueryDirectiveEntry(LoaderModel):
    """An interpretant's `query:` annotation (FR-CO-03, FR-RT-11, FR-RT-15, FR-EX-01–05).
    `directive` is free text; v1 code interprets `"filter"` (requires `as_token`,
    excluded from the plain query), `"exact"` (kept in the plain query, `as_token`
    optional and defaults to `value`), and `"skip"` (excludes the interpretant from
    retrieval entirely; `as_token` unused)."""

    directive: str
    as_token: str = ""


class InterpretantEntry(LoaderModel):
    """One `interpretants:` list entry (FR-SD-05). `type` is a free-text,
    descriptive-only label (e.g. "concept", "foundation", "numeric_value") —
    it does not gate retrieval eligibility and is never part of matching
    identity, which is keyed by `value` alone."""

    type: str = "concept"
    value: str
    query: QueryDirectiveEntry | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _normalize_value(cls, value: object) -> object:
        return _normalize_authored_value(value)


class IntersemioticInterpretantEntry(LoaderModel):
    """One inline intersemiotic interpretant (FR-SD-04) — `target_sign`/`according_to`
    are human-readable names resolved against already-parsed signs/traditions by
    the loader (FR-SD-03). `target_system` scopes `target_sign` resolution to signs
    declared under that `semiotic_system`."""

    target_system: str
    target_sign: str
    relationship: str
    according_to: str
    description: str = ""
    symmetric: bool = False
    confidence: str = "attributed"


class ManifestationEntry(LoaderModel):
    """One `manifestations:` list entry (FR-DM-02). `tradition` names a `Tradition` by
    slug or name (FR-SD-03); `cites` is a free-text citation resolved against loaded
    sources (see `sign_loader._resolve_citation`)."""

    tradition: str
    display_name: str
    denotation: str = ""
    cites: tuple[str, ...] = ()
    properties: tuple[PropertyEntry, ...] = ()
    interpretants: tuple[InterpretantEntry, ...] = ()
    intersemiotic_interpretants: tuple[IntersemioticInterpretantEntry, ...] = ()

    @field_validator("cites", mode="before")
    @classmethod
    def _coerce_single_cites_to_tuple(cls, value: object) -> object:
        """`cites: "..."` (a single string) is sugar for a one-element list —
        matches the worked example in `specs/domain/domain-model.md`, which
        shows the common case of a single citation without requiring a
        curator to wrap it in `[...]`."""
        return (value,) if isinstance(value, str) else value


class SignBlock(LoaderModel):
    """`id` is accepted so a file copying `docs/newmodel.yaml`'s worked example
    verbatim does not fail shape validation — it is never read by the loader.
    A sign's real id/slug is always its file's stem (see `sign_loader.py`).

    `manifestations` is entirely optional (FR-DM-05) — a sign may exist purely as a
    correspondence target/anchor."""

    id: str | None = None
    name: str
    type: str
    notes: str = ""
    properties: tuple[PropertyEntry, ...] = ()
    manifestations: tuple[ManifestationEntry, ...] = ()


class SignFile(LoaderModel):
    """`data/<domain>/signs/<slug>.yaml` — the filename stem is the slug."""

    semiotic_system: str
    sign: SignBlock
