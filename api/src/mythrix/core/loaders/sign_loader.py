# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Loads a directory of human-authored structured-data YAML (see
`sign_schema.py`) into a `KuzuGraphStore`, resolving name-based references
(FR-SD-03), validating referential integrity *before* writing anything (FR-SD-01, FR-SD-02),
and upserting idempotently.

Two-pass design: pass 1 parses every file and resolves every reference (`tradition:`,
`cites:`, `intersemiotic_interpretants.target_sign`/`.according_to`) purely in memory;
pass 2 writes, and only runs if pass 1 raised nothing. This is what makes "nothing is
written until every reference in the file resolves" (FR-SD-02) true even for a reference in
the *last* file of a large directory.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

import yaml

from mythrix.core.errors import IngestValidationError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.loaders.sign_schema import SignFile, SourceFile, TraditionFile
from mythrix.core.models import Citation, Interpretant, Manifestation, Property, QueryDirective, Sign, Source, Tradition

_T = TypeVar("_T")

_STOPWORDS = frozenset({"the", "a", "an", "of", "and"})


def _tokenize(text: str) -> frozenset[str]:
    return frozenset(tok for tok in re.split(r"[^a-z0-9]+", text.lower()) if tok and tok not in _STOPWORDS)


@dataclass(frozen=True)
class _Candidate:
    """One resolvable entity, reduced to the fields name-resolution needs."""

    value: _T
    slug: str
    primary_name: str
    search_text: str


def _resolve(query: str, candidates: Sequence[_Candidate], *, kind: str, context: str) -> _T:
    """Tiered name resolution (FR-SD-03): exact slug, then exact case-insensitive name,
    then a forgiving word-subset match (every significant word in `query` must
    appear in the candidate's searchable text) — this last tier is what lets an
    informal reference like `according_to: "Golden Dawn"` resolve against a
    tradition named "Golden Dawn Kabbalah". Raises with the offending name and
    file context on zero or multiple matches at whichever tier produced results.
    """
    tiers: list[list[_Candidate]] = [
        [c for c in candidates if c.slug == query],
        [c for c in candidates if c.primary_name.casefold() == query.casefold()],
    ]
    query_tokens = _tokenize(query)
    if query_tokens:
        tiers.append([c for c in candidates if query_tokens <= _tokenize(c.search_text)])

    for tier in tiers:
        if len(tier) == 1:
            return tier[0].value
        if len(tier) > 1:
            raise IngestValidationError(
                f"Ambiguous {kind} reference {query!r}: matches {len(tier)} candidates.", source_path=context
            )
    raise IngestValidationError(
        f"Unresolved {kind} reference {query!r}: no matching {kind} found.", source_path=context
    )


def _resolve_citation(cites: str, sources: Sequence[_Candidate], *, context: str) -> Citation:
    """`cites` is one free-text string in "Author, Title[, Locator]" form, e.g.
    `"Waite, Pictorial Key to the Tarot, p. 97"` or `"Waite, Pictorial Key to
    the Tarot, Part II -- XVI. The Tower"`. The source reference is always the
    *first two* comma-separated segments (author, title) — resolved against
    loaded sources via `_resolve`'s word-subset tier (title+author combined),
    since an informal citation rarely matches a source's `title` field
    verbatim. Everything after the second comma is the locator, verbatim, even
    if it contains further commas of its own (e.g. "Chapter 4, Section 2") —
    splitting on the *last* comma instead would misread such a locator as part
    of the source reference. Fewer than two commas means there's no locator at
    all: the whole string is the source reference.
    """
    parts = cites.split(",", 2)
    if len(parts) < 3:
        source_query, locator = cites.strip(), ""
    else:
        source_query, locator = ",".join(parts[:2]).strip(), parts[2].strip()
    source = _resolve(source_query, sources, kind="source", context=context)
    return Citation(source=source, locator=locator)


@dataclass
class _PendingIntersemioticInterpretant:
    from_sign_id: str
    to_sign_id: str
    relationship: str
    according_to_id: str
    description: str = ""
    symmetric: bool = False
    confidence: str = "attributed"
    source_id: str = ""


@dataclass
class LoadPlan:
    """Everything resolved and ready to write — produced by pass 1, consumed by
    pass 2. Kept as a plain data holder so pass 1 (validation) and pass 2 (writes)
    stay clearly separated in `load_directory`."""

    traditions: list[Tradition] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    bare_signs: list[Sign] = field(default_factory=list)
    manifestations: list[tuple[Sign, Manifestation]] = field(default_factory=list)
    intersemiotic_interpretants: list[_PendingIntersemioticInterpretant] = field(default_factory=list)


def summarize_plan(plan: LoadPlan) -> dict[str, int]:
    """Counts for a `LoadPlan`, shared by every caller that reports what
    was/would be loaded (`cli/commands/load_signs.py`, `api/routes.py`'s
    `/reload-signs`) — one summary shape regardless of which process ran
    `build_plan`/`load_directory`."""
    return {
        "traditions": len(plan.traditions),
        "sources": len(plan.sources),
        "signs": len(plan.bare_signs),
        "manifestations": len(plan.manifestations),
        "intersemiotic_interpretants": len(plan.intersemiotic_interpretants),
    }


def _read_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _load_traditions(paths: Iterable[Path]) -> list[Tradition]:
    traditions = []
    for path in paths:
        try:
            parsed = TraditionFile.model_validate(_read_yaml(path))
        except Exception as exc:  # noqa: BLE001 - re-raised with file context below
            raise IngestValidationError(str(exc), source_path=str(path)) from exc
        slug = path.stem
        traditions.append(
            Tradition(
                id=slug,
                slug=slug,
                name=parsed.tradition.name,
                domain=parsed.tradition.domain,
                description=parsed.tradition.description,
            )
        )
    _reject_duplicate_slugs([t.slug for t in traditions], kind="tradition")
    return traditions


def _load_sources(paths: Iterable[Path]) -> list[Source]:
    sources = []
    for path in paths:
        try:
            parsed = SourceFile.model_validate(_read_yaml(path))
        except Exception as exc:  # noqa: BLE001 - re-raised with file context below
            raise IngestValidationError(str(exc), source_path=str(path)) from exc
        sources.append(
            Source(
                id=parsed.source.id,
                domain=parsed.source.domain,
                citation_label=parsed.source.citation_label,
                title=parsed.source.title,
                author=parsed.source.author,
                publication_year=parsed.source.publication_year,
                license=parsed.source.license,
                uri=parsed.source.uri,
                description=parsed.source.description,
            )
        )
    _reject_duplicate_slugs([s.id for s in sources], kind="source")
    return sources


def _reject_duplicate_slugs(slugs: Sequence[str], *, kind: str) -> None:
    seen: set[str] = set()
    for slug in slugs:
        if slug in seen:
            raise IngestValidationError(f"Duplicate {kind} slug {slug!r}.")
        seen.add(slug)


def _tradition_candidates(traditions: Sequence[Tradition]) -> list[_Candidate]:
    return [_Candidate(value=t, slug=t.slug, primary_name=t.name, search_text=f"{t.slug} {t.name}") for t in traditions]


def _source_candidates(sources: Sequence[Source]) -> list[_Candidate]:
    return [_Candidate(value=s, slug=s.id, primary_name=s.title, search_text=f"{s.title} {s.author}") for s in sources]


def _sign_candidates(signs: Sequence[Sign], *, semiotic_system: str) -> list[_Candidate]:
    """Signs declared under one named `semiotic_system` only — an
    intersemiotic interpretant's target is resolved against this narrowed
    pool rather than every parsed sign (FR-SD-03), so two systems each having a
    sign of the same or similar name can never be ambiguous with each other."""
    return [
        _Candidate(value=s, slug=s.slug, primary_name=s.canonical_name, search_text=s.canonical_name)
        for s in signs
        if s.semiotic_system == semiotic_system
    ]


def load_directory(root: Path, store: KuzuGraphStore) -> LoadPlan:
    """Loads every tradition/source/sign YAML file found anywhere under `root`
    (searched recursively, so `root` may be a single domain directory or a parent
    of several), in dependency order, validating all name-based references (FR-SD-03)
    and referential integrity (FR-SD-01, FR-SD-02) before writing anything to `store`.

    Raises `IngestValidationError` — with nothing written to `store` — on any
    schema error, unresolvable/ambiguous name reference, duplicate slug, or
    target semiotic system with no matching sign.

    Returns the `LoadPlan` that was written — `cli/commands/load_signs.py`
    uses this (and the standalone `build_plan()` below, for `--dry-run`) to
    report what was/would be loaded.
    """
    plan = build_plan(root)
    _write_plan(plan, store)
    return plan


def build_plan(root: Path) -> LoadPlan:  # noqa: C901 - one cohesive validation pass, deliberately not split further
    plan = LoadPlan()
    plan.traditions = _load_traditions(sorted(root.rglob("traditions/*.yaml")))
    plan.sources = _load_sources(sorted(root.rglob("sources/*.yaml")))

    tradition_candidates = _tradition_candidates(plan.traditions)
    source_candidates = _source_candidates(plan.sources)

    sign_paths = sorted(root.rglob("signs/*.yaml"))
    parsed_sign_files: list[tuple[Path, str, SignFile]] = []
    for path in sign_paths:
        try:
            parsed = SignFile.model_validate(_read_yaml(path))
        except Exception as exc:  # noqa: BLE001 - re-raised with file context below
            raise IngestValidationError(str(exc), source_path=str(path)) from exc
        slug = path.stem
        properties = tuple(
            Property(
                id=f"{slug}::property::{prop.key}",
                key=prop.key,
                value=prop.value,
            )
            for prop in parsed.sign.properties
        )
        sign = Sign(
            id=slug,
            slug=slug,
            canonical_name=parsed.sign.name,
            sign_type=parsed.sign.type,
            semiotic_system=parsed.semiotic_system,
            notes=parsed.sign.notes,
            properties=properties,
        )
        plan.bare_signs.append(sign)
        parsed_sign_files.append((path, slug, parsed))

    _reject_duplicate_slugs([s.slug for s in plan.bare_signs], kind="sign")
    signs_by_slug = {s.slug: s for s in plan.bare_signs}

    for path, slug, parsed in parsed_sign_files:
        sign = signs_by_slug[slug]
        for entry in parsed.sign.manifestations:
            tradition = _resolve(entry.tradition, tradition_candidates, kind="tradition", context=str(path))
            manifestation_properties = tuple(
                Property(
                    id=f"{slug}::{tradition.slug}::property::{p.key}",
                    key=p.key,
                    value=p.value,
                )
                for p in entry.properties
            )
            interpretants = tuple(
                Interpretant(
                    id=f"{slug}::{tradition.slug}::interpretant::{i}",
                    type=interpretant.type,
                    value=interpretant.value,
                    position=i,
                    query=QueryDirective(directive=interpretant.query.directive, as_token=interpretant.query.as_token)
                    if interpretant.query
                    else None,
                )
                for i, interpretant in enumerate(entry.interpretants)
            )
            citations = tuple(_resolve_citation(cites, source_candidates, context=str(path)) for cites in entry.cites)
            manifestation = Manifestation(
                id=f"{slug}::{tradition.slug}",
                sign_id=sign.id,
                tradition=tradition,
                display_name=entry.display_name,
                denotation=entry.denotation,
                properties=manifestation_properties,
                interpretants=interpretants,
                citations=citations,
                created_at=datetime.now(UTC),
            )
            plan.manifestations.append((sign, manifestation))

            for correspondence in entry.intersemiotic_interpretants:
                system_candidates = _sign_candidates(plan.bare_signs, semiotic_system=correspondence.target_system)
                if not system_candidates:
                    raise IngestValidationError(
                        f"No sign found in semiotic system {correspondence.target_system!r}.", source_path=str(path)
                    )
                target = _resolve(correspondence.target_sign, system_candidates, kind="sign", context=str(path))
                according_to = _resolve(
                    correspondence.according_to, tradition_candidates, kind="tradition", context=str(path)
                )
                plan.intersemiotic_interpretants.append(
                    _PendingIntersemioticInterpretant(
                        from_sign_id=sign.id,
                        to_sign_id=target.id,
                        relationship=correspondence.relationship,
                        according_to_id=according_to.id,
                        description=correspondence.description,
                        symmetric=correspondence.symmetric,
                        confidence=correspondence.confidence,
                    )
                )

    return plan


def _write_plan(plan: LoadPlan, store: KuzuGraphStore) -> None:
    for tradition in plan.traditions:
        store.upsert_tradition(tradition)
    for source in plan.sources:
        store.upsert_source(source)

    manifested_sign_ids = {sign.id for sign, _ in plan.manifestations}
    for sign in plan.bare_signs:
        if sign.id not in manifested_sign_ids:
            store.upsert_sign(sign)
    for sign, manifestation in plan.manifestations:
        store.upsert_sign_with_manifestation(sign, manifestation)

    # Reconcile each sign's Manifestation set against what's currently
    # declared in the YAML — e.g. so renaming the tradition a manifestation
    # belongs to (which changes the manifestation's own id) doesn't leave the
    # old one orphaned but still linked. Grouped per sign since a sign can
    # legitimately have several manifestations across different traditions.
    current_manifestation_ids_by_sign: dict[str, set[str]] = {}
    for sign, manifestation in plan.manifestations:
        current_manifestation_ids_by_sign.setdefault(sign.id, set()).add(manifestation.id)
    for sign_id, current_ids in current_manifestation_ids_by_sign.items():
        store.reconcile_sign_manifestations(sign_id, frozenset(current_ids))
    for sign in plan.bare_signs:
        if sign.id not in manifested_sign_ids:
            store.reconcile_sign_manifestations(sign.id, frozenset())

    for interpretant in plan.intersemiotic_interpretants:
        store.upsert_intersemiotic_interpretant(
            from_sign_id=interpretant.from_sign_id,
            to_sign_id=interpretant.to_sign_id,
            relationship=interpretant.relationship,
            according_to_id=interpretant.according_to_id,
            description=interpretant.description,
            symmetric=interpretant.symmetric,
            confidence=interpretant.confidence,
            source_id=interpretant.source_id,
        )
