"""Loads a directory of human-authored structured-data YAML (see
`symbol_schema.py`) into a `KuzuGraphStore`, resolving name-based references
(FR18), validating referential integrity *before* writing anything (FR4, FR5),
and upserting idempotently.

Two-pass design: pass 1 parses every file and resolves every reference (`tradition:`,
`cites:`, `corresponds_to.to`/`according_to`) purely in memory; pass 2 writes,
and only runs if pass 1 raised nothing. This is what makes "nothing is written
until every reference in the file resolves" (FR5) true even for a reference in
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
from mythrix.core.loaders.symbol_schema import SourceFile, SymbolFile, TraditionFile
from mythrix.core.models import Attribute, Citation, Interpretation, Source, Symbol, Tradition

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
    """Tiered name resolution (FR18): exact slug, then exact case-insensitive name,
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
class _PendingRelationship:
    from_symbol_id: str
    to_symbol_id: str
    relationship_type: str
    according_to_tradition_id: str
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
    bare_symbols: list[Symbol] = field(default_factory=list)
    interpretations: list[tuple[Symbol, Interpretation]] = field(default_factory=list)
    relationships: list[_PendingRelationship] = field(default_factory=list)


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
        slug = path.stem
        sources.append(
            Source(
                id=slug,
                title=parsed.source.title,
                author=parsed.source.author,
                publication_year=parsed.source.publication_year,
                license=parsed.source.license,
                uri=parsed.source.uri,
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


def _symbol_candidates(symbols: Sequence[Symbol]) -> list[_Candidate]:
    return [
        _Candidate(value=s, slug=s.slug, primary_name=s.canonical_name, search_text=s.canonical_name) for s in symbols
    ]


def load_directory(root: Path, store: KuzuGraphStore) -> LoadPlan:
    """Loads every tradition/source/symbol YAML file found anywhere under `root`
    (searched recursively, so `root` may be a single domain directory or a parent
    of several), in dependency order, validating all name-based references (FR18)
    and referential integrity (FR4, FR5) before writing anything to `store`.

    Raises `IngestValidationError` — with nothing written to `store` — on any
    schema error, unresolvable/ambiguous name reference, or duplicate slug.

    Returns the `LoadPlan` that was written — `cli/commands/load_symbols.py`
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

    symbol_paths = sorted(root.rglob("symbols/*.yaml"))
    parsed_symbol_files: list[tuple[Path, str, SymbolFile]] = []
    for path in symbol_paths:
        try:
            parsed = SymbolFile.model_validate(_read_yaml(path))
        except Exception as exc:  # noqa: BLE001 - re-raised with file context below
            raise IngestValidationError(str(exc), source_path=str(path)) from exc
        slug = path.stem
        properties = tuple(
            Attribute(
                id=f"{slug}::property::{prop.key}",
                key=prop.key,
                value=prop.value,
                value_type=prop.value_type,
                retrievable=prop.retrievable,
            )
            for prop in parsed.symbol.properties
        )
        symbol = Symbol(
            id=slug,
            slug=slug,
            canonical_name=parsed.symbol.name,
            symbol_type=parsed.symbol.type,
            notes=parsed.symbol.notes,
            properties=properties,
        )
        plan.bare_symbols.append(symbol)
        parsed_symbol_files.append((path, slug, parsed))

    _reject_duplicate_slugs([s.slug for s in plan.bare_symbols], kind="symbol")
    symbol_candidates = _symbol_candidates(plan.bare_symbols)
    symbols_by_slug = {s.slug: s for s in plan.bare_symbols}

    for path, slug, parsed in parsed_symbol_files:
        symbol = symbols_by_slug[slug]
        for entry in parsed.interpretations:
            tradition = _resolve(entry.tradition, tradition_candidates, kind="tradition", context=str(path))
            interpretation_attributes = [
                Attribute(
                    id=f"{slug}::{tradition.slug}::attribute::{a.key}",
                    key=a.key,
                    value=a.value,
                    value_type=a.value_type,
                    retrievable=a.retrievable,
                )
                for a in entry.attributes
            ]
            interpretation_attributes += [
                Attribute(id=f"{slug}::{tradition.slug}::keyword::{i}", key="keyword", value=keyword, position=i)
                for i, keyword in enumerate(entry.keywords)
            ]
            citations = tuple(_resolve_citation(cites, source_candidates, context=str(path)) for cites in entry.cites)
            interpretation = Interpretation(
                id=f"{slug}::{tradition.slug}",
                symbol_id=symbol.id,
                tradition=tradition,
                display_name=entry.display_name,
                summary=entry.summary,
                attributes=tuple(interpretation_attributes),
                citations=citations,
                created_at=datetime.now(UTC),
            )
            plan.interpretations.append((symbol, interpretation))

            for correspondence in entry.corresponds_to:
                target = _resolve(correspondence.to, symbol_candidates, kind="symbol", context=str(path))
                according_to = _resolve(
                    correspondence.according_to, tradition_candidates, kind="tradition", context=str(path)
                )
                plan.relationships.append(
                    _PendingRelationship(
                        from_symbol_id=symbol.id,
                        to_symbol_id=target.id,
                        relationship_type=correspondence.relationship,
                        according_to_tradition_id=according_to.id,
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

    interpreted_symbol_ids = {symbol.id for symbol, _ in plan.interpretations}
    for symbol in plan.bare_symbols:
        if symbol.id not in interpreted_symbol_ids:
            store.upsert_symbol(symbol)
    for symbol, interpretation in plan.interpretations:
        store.upsert_symbol_with_interpretation(symbol, interpretation)

    # Reconcile each symbol's Interpretation set against what's currently
    # declared in the YAML — e.g. so renaming the tradition an interpretation
    # belongs to (which changes the interpretation's own id) doesn't leave the
    # old one orphaned but still linked. Grouped per symbol since a symbol can
    # legitimately have several interpretations across different traditions.
    current_interpretation_ids_by_symbol: dict[str, set[str]] = {}
    for symbol, interpretation in plan.interpretations:
        current_interpretation_ids_by_symbol.setdefault(symbol.id, set()).add(interpretation.id)
    for symbol_id, current_ids in current_interpretation_ids_by_symbol.items():
        store.reconcile_symbol_interpretations(symbol_id, frozenset(current_ids))
    for symbol in plan.bare_symbols:
        if symbol.id not in interpreted_symbol_ids:
            store.reconcile_symbol_interpretations(symbol.id, frozenset())

    for relationship in plan.relationships:
        store.upsert_relationship(
            from_symbol_id=relationship.from_symbol_id,
            to_symbol_id=relationship.to_symbol_id,
            relationship_type=relationship.relationship_type,
            according_to_tradition_id=relationship.according_to_tradition_id,
            description=relationship.description,
            symmetric=relationship.symmetric,
            confidence=relationship.confidence,
            source_id=relationship.source_id,
        )
