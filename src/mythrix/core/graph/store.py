"""KuzuGraphStore: deterministic, parametrized access to the Symbol Graph.

Retrieval methods here are the concrete implementation of the anti-hallucination
boundary: they only ever run parametrized Cypher built from plain Python control
flow, never from LLM output or unvalidated free text (FR10). Retrieval composes
several small, focused queries in Python rather than one large aggregate query with
nested struct collections — simpler to test and reason about, and avoids relying on
Cypher features not needed anywhere else in this codebase.

Upserts use Kùzu's `MERGE ... ON CREATE SET ... ON MATCH SET ...`, which is idempotent
against the pinned Kùzu version (see tests/unit/test_graph_store.py) — no custom
exists-then-insert/update logic is needed, contrary to what plan.md's Risks section
anticipated before this was verified.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import kuzu

from mythrix.core.errors import (
    InterpretationNotFoundError,
    SourceNotFoundError,
    SymbolNotFoundError,
    TraditionNotFoundError,
)
from mythrix.core.graph.schema import create_schema
from mythrix.core.models import (
    Attribute,
    Citation,
    GraphFacts,
    Interpretation,
    RelationshipFact,
    Source,
    Symbol,
    Tradition,
)


def _s(value: str | None) -> str:
    """Kùzu returns unset STRING columns as None; our models default to ""."""
    return value or ""


def _attribute_from_row(row: list[Any]) -> Attribute:
    """Shared by every query that returns `a.id, a.key, a.value, a.value_type,
    a.position, a.retrievable` in that order — a row layout that recurs across
    `_fetch_attributes`/`_get_all_interpretation_attributes`."""
    return Attribute(
        id=row[0],
        key=row[1],
        value=row[2],
        value_type=_s(row[3]) or "string",
        position=row[4] or 0,
        retrievable=row[5] if row[5] is not None else True,
    )


class KuzuGraphStore:
    """Owns a Kùzu database connection; exposes idempotent upserts and the
    deterministic `get_interpretation` retrieval query."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._database = kuzu.Database(str(db_path))
        self._connection = kuzu.Connection(self._database)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        existing = {row[1] for row in self._connection.execute("CALL show_tables() RETURN *")}
        if "Symbol" not in existing:
            create_schema(self._connection)

    def _execute(self, query: str, parameters: dict[str, Any]) -> Any:
        return self._connection.execute(query, parameters=parameters)

    # -- Upserts -----------------------------------------------------------------

    def upsert_tradition(self, tradition: Tradition) -> None:
        self._execute(
            """
            MERGE (t:Tradition {id: $id})
            ON CREATE SET t.slug = $slug, t.name = $name, t.domain = $domain, t.description = $description
            ON MATCH SET t.slug = $slug, t.name = $name, t.domain = $domain, t.description = $description
            """,
            {
                "id": tradition.id,
                "slug": tradition.slug,
                "name": tradition.name,
                "domain": tradition.domain,
                "description": tradition.description,
            },
        )

    def upsert_source(self, source: Source) -> None:
        self._execute(
            """
            MERGE (s:Source {id: $id})
            ON CREATE SET s.title = $title, s.author = $author, s.publication_year = $publication_year,
                          s.license = $license, s.uri = $uri, s.content_hash = $content_hash,
                          s.ingested_at = $ingested_at
            ON MATCH SET s.title = $title, s.author = $author, s.publication_year = $publication_year,
                         s.license = $license, s.uri = $uri, s.content_hash = $content_hash,
                         s.ingested_at = $ingested_at
            """,
            {
                "id": source.id,
                "title": source.title,
                "author": source.author,
                "publication_year": source.publication_year,
                "license": source.license,
                "uri": source.uri,
                "content_hash": source.content_hash,
                "ingested_at": source.ingested_at,
            },
        )

    def _upsert_attribute(self, attribute: Attribute) -> None:
        """Shared by both symbol-intrinsic `properties` and interpretation-scoped
        `attributes` — an `Attribute` node's own fields don't depend on which kind of
        node points at it; only the `HAS_ATTRIBUTE` edge's source differs."""
        self._execute(
            """
            MERGE (a:Attribute {id: $id})
            ON CREATE SET a.key = $key, a.value = $value, a.value_type = $value_type,
                          a.position = $position, a.retrievable = $retrievable
            ON MATCH SET a.key = $key, a.value = $value, a.value_type = $value_type,
                         a.position = $position, a.retrievable = $retrievable
            """,
            {
                "id": attribute.id,
                "key": attribute.key,
                "value": attribute.value,
                "value_type": attribute.value_type,
                "position": attribute.position,
                "retrievable": attribute.retrievable,
            },
        )

    def upsert_symbol(self, symbol: Symbol) -> None:
        """Writes just the Symbol node and its intrinsic `properties` — no
        Interpretation. Interpretations are optional (a symbol may exist purely as a
        correspondence target/anchor, e.g. a Tree of Life path never given its own
        tradition-scoped meaning); use `upsert_symbol_with_interpretation` when the
        symbol does have one to record.
        """
        self._execute(
            """
            MERGE (s:Symbol {id: $id})
            ON CREATE SET s.slug = $slug, s.canonical_name = $canonical_name,
                          s.symbol_type = $symbol_type, s.notes = $notes
            ON MATCH SET s.slug = $slug, s.canonical_name = $canonical_name,
                         s.symbol_type = $symbol_type, s.notes = $notes
            """,
            {
                "id": symbol.id,
                "slug": symbol.slug,
                "canonical_name": symbol.canonical_name,
                "symbol_type": symbol.symbol_type,
                "notes": symbol.notes,
            },
        )

        # An Attribute's id is derived from its key (see symbol_loader.py), so
        # renaming or removing one in the YAML produces a different id — MERGE
        # alone would leave the old Attribute node orphaned but still linked
        # forever. Replace the full set on every load instead of merging it,
        # since each call already carries the complete current properties.
        self._execute(
            "MATCH (s:Symbol {id: $id})-[e:HAS_ATTRIBUTE]->(a:Attribute) DELETE e, a",
            {"id": symbol.id},
        )
        for prop in symbol.properties:
            self._upsert_attribute(prop)
            self._execute(
                """
                MATCH (s:Symbol {id: $symbol_id}), (a:Attribute {id: $attribute_id})
                MERGE (s)-[:HAS_ATTRIBUTE]->(a)
                """,
                {"symbol_id": symbol.id, "attribute_id": prop.id},
            )

    def upsert_symbol_with_interpretation(self, symbol: Symbol, interpretation: Interpretation) -> None:
        """Writes the Symbol (via `upsert_symbol`) plus the Interpretation (scoped to
        `interpretation.tradition`) and all of its tradition-scoped attributes and
        citations.

        The interpretation's tradition and every cited source must already exist
        (call upsert_tradition/upsert_source first) — this method does not validate
        referential integrity; that's the structured-data loader's job (FR4, FR5).
        """
        self.upsert_symbol(symbol)

        self._execute(
            """
            MERGE (i:Interpretation {id: $id})
            ON CREATE SET i.symbol_id = $symbol_id, i.tradition_id = $tradition_id,
                          i.display_name = $display_name, i.summary = $summary, i.created_at = $created_at
            ON MATCH SET i.symbol_id = $symbol_id, i.tradition_id = $tradition_id,
                         i.display_name = $display_name, i.summary = $summary, i.created_at = $created_at
            """,
            {
                "id": interpretation.id,
                "symbol_id": symbol.id,
                "tradition_id": interpretation.tradition.id,
                "display_name": interpretation.display_name,
                "summary": interpretation.summary,
                "created_at": interpretation.created_at,
            },
        )

        self._execute(
            """
            MATCH (s:Symbol {id: $symbol_id}), (i:Interpretation {id: $interpretation_id})
            MERGE (s)-[:HAS_INTERPRETATION]->(i)
            """,
            {"symbol_id": symbol.id, "interpretation_id": interpretation.id},
        )
        self._execute(
            """
            MATCH (i:Interpretation {id: $interpretation_id}), (t:Tradition {id: $tradition_id})
            MERGE (i)-[:INTERPRETED_IN]->(t)
            """,
            {"interpretation_id": interpretation.id, "tradition_id": interpretation.tradition.id},
        )

        # Same reconciliation as `upsert_symbol`'s properties, and for the same
        # reason: an attribute's id is derived from its key, so a renamed or
        # removed one would otherwise leave a stale node orphaned but linked.
        self._execute(
            "MATCH (i:Interpretation {id: $id})-[e:HAS_ATTRIBUTE]->(a:Attribute) DELETE e, a",
            {"id": interpretation.id},
        )
        for attribute in interpretation.attributes:
            self._upsert_attribute(attribute)
            self._execute(
                """
                MATCH (i:Interpretation {id: $interpretation_id}), (a:Attribute {id: $attribute_id})
                MERGE (i)-[:HAS_ATTRIBUTE]->(a)
                """,
                {"interpretation_id": interpretation.id, "attribute_id": attribute.id},
            )

        for citation in interpretation.citations:
            self._execute(
                """
                MATCH (i:Interpretation {id: $interpretation_id}), (src:Source {id: $source_id})
                MERGE (i)-[r:CITES]->(src)
                ON CREATE SET r.locator = $locator
                ON MATCH SET r.locator = $locator
                """,
                {
                    "interpretation_id": interpretation.id,
                    "source_id": citation.source.id,
                    "locator": citation.locator,
                },
            )

    def reconcile_symbol_interpretations(self, symbol_id: str, current_interpretation_ids: frozenset[str]) -> None:
        """Deletes any Interpretation still linked to this symbol whose id isn't
        in `current_interpretation_ids` (plus everything scoped to it — its own
        attributes, `HAS_INTERPRETATION`/`INTERPRETED_IN`/`CITES` edges).

        An Interpretation's id is derived from its symbol *and* tradition slug
        (`symbol_loader.py`), so renaming the tradition an interpretation
        belongs to changes the interpretation's own id — without this, the old
        node would be left orphaned but still linked forever, the same class
        of bug attribute-key renames had (see `upsert_symbol`'s reconciliation).
        Must be called once per symbol with its *complete* current set, after
        every interpretation for that symbol has been written this load — not
        from inside `upsert_symbol_with_interpretation` itself, which only ever
        sees one interpretation at a time and would delete its own siblings.
        """
        result = self._execute(
            "MATCH (:Symbol {id: $id})-[:HAS_INTERPRETATION]->(i:Interpretation) RETURN i.id",
            {"id": symbol_id},
        )
        stale_ids = []
        while result.has_next():
            (interpretation_id,) = result.get_next()
            if interpretation_id not in current_interpretation_ids:
                stale_ids.append(interpretation_id)
        for interpretation_id in stale_ids:
            self._execute(
                "MATCH (i:Interpretation {id: $id})-[e:HAS_ATTRIBUTE]->(a:Attribute) DELETE e, a",
                {"id": interpretation_id},
            )
            self._execute("MATCH (i:Interpretation {id: $id}) DETACH DELETE i", {"id": interpretation_id})

    def upsert_relationship(
        self,
        *,
        from_symbol_id: str,
        to_symbol_id: str,
        relationship_type: str,
        according_to_tradition_id: str,
        description: str = "",
        symmetric: bool = False,
        confidence: str = "attributed",
        source_id: str = "",
    ) -> None:
        """Idempotent per (from, to, relationship_type, according_to_tradition_id) —
        re-running with the same identity updates description/confidence/etc. in
        place; a *different* according_to_tradition_id adds a new, independent claim
        rather than overwriting the first (FR3; verified in
        tests/unit/test_kuzu_multi_edge_risk.py).

        Connects `Symbol -> Symbol` directly, not through either endpoint's
        `Interpretation` — a symbol with zero interpretations can still be a valid
        `to_symbol_id`/`from_symbol_id`.
        """
        self._execute(
            """
            MATCH (a:Symbol {id: $from_id}), (b:Symbol {id: $to_id})
            MERGE (a)-[r:RELATES_TO {
                relationship_type: $relationship_type,
                according_to_tradition_id: $according_to_tradition_id
            }]->(b)
            ON CREATE SET r.description = $description, r.symmetric = $symmetric,
                          r.confidence = $confidence, r.source_id = $source_id
            ON MATCH SET r.description = $description, r.symmetric = $symmetric,
                         r.confidence = $confidence, r.source_id = $source_id
            """,
            {
                "from_id": from_symbol_id,
                "to_id": to_symbol_id,
                "relationship_type": relationship_type,
                "according_to_tradition_id": according_to_tradition_id,
                "description": description,
                "symmetric": symmetric,
                "confidence": confidence,
                "source_id": source_id,
            },
        )

    # -- Retrieval -----------------------------------------------------------------

    def get_interpretation(self, symbol_slug: str, tradition_slug: str) -> GraphFacts:
        """Deterministic, parametrized retrieval of one symbol's interpretation
        within one tradition (FR9, FR10) — never generated from LLM output."""
        symbol = self._get_symbol_by_slug(symbol_slug)
        tradition = self._get_tradition_by_slug(tradition_slug)

        result = self._execute(
            """
            MATCH (s:Symbol {id: $symbol_id})-[:HAS_INTERPRETATION]->(i:Interpretation)
                  -[:INTERPRETED_IN]->(t:Tradition {id: $tradition_id})
            RETURN i.id, i.display_name, i.summary, i.created_at
            """,
            {"symbol_id": symbol.id, "tradition_id": tradition.id},
        )
        if not result.has_next():
            raise InterpretationNotFoundError(symbol_slug, tradition_slug)
        interpretation_id, display_name, summary, created_at = result.get_next()

        interpretation = Interpretation(
            id=interpretation_id,
            symbol_id=symbol.id,
            tradition=tradition,
            display_name=display_name,
            summary=_s(summary),
            attributes=self._get_attributes(interpretation_id),
            citations=self._get_citations(interpretation_id),
            created_at=created_at,
        )
        # Correspondences belong to the symbol, not this specific interpretation (see
        # Symbol.relationships docstring) — populated here via model_copy since
        # _get_symbol_by_slug/_get_symbol_by_id deliberately return relationship
        # targets shallow, to avoid unbounded recursion through RelationshipFact.
        symbol = symbol.model_copy(update={"relationships": self._get_symbol_relationships(symbol.id)})
        return GraphFacts(symbol=symbol, interpretation=interpretation)

    # -- Internal lookups -----------------------------------------------------------------

    def _get_symbol_by_slug(self, slug: str) -> Symbol:
        result = self._execute(
            "MATCH (s:Symbol {slug: $slug}) RETURN s.id, s.slug, s.canonical_name, s.symbol_type, s.notes",
            {"slug": slug},
        )
        if not result.has_next():
            raise SymbolNotFoundError(slug)
        row = result.get_next()
        return Symbol(
            id=row[0],
            slug=row[1],
            canonical_name=row[2],
            symbol_type=row[3],
            notes=_s(row[4]),
            properties=self._get_symbol_properties(row[0]),
        )

    def _get_symbol_by_id(self, symbol_id: str) -> Symbol:
        row = self._execute(
            "MATCH (s:Symbol {id: $id}) RETURN s.id, s.slug, s.canonical_name, s.symbol_type, s.notes",
            {"id": symbol_id},
        ).get_next()
        return Symbol(
            id=row[0],
            slug=row[1],
            canonical_name=row[2],
            symbol_type=row[3],
            notes=_s(row[4]),
            properties=self._get_symbol_properties(row[0]),
        )

    def get_tradition(self, tradition_slug: str) -> Tradition:
        """Public lookup used by the retrieval pipeline (T15) to hydrate a
        `VectorHit.tradition_slug` into a full `Tradition` for `RetrievedPassage`."""
        return self._get_tradition_by_slug(tradition_slug)

    def _get_tradition_by_slug(self, slug: str) -> Tradition:
        result = self._execute(
            "MATCH (t:Tradition {slug: $slug}) RETURN t.id, t.slug, t.name, t.domain, t.description",
            {"slug": slug},
        )
        if not result.has_next():
            raise TraditionNotFoundError(slug)
        row = result.get_next()
        return Tradition(id=row[0], slug=row[1], name=row[2], domain=row[3], description=_s(row[4]))

    def _get_tradition_by_id(self, tradition_id: str) -> Tradition:
        row = self._execute(
            "MATCH (t:Tradition {id: $id}) RETURN t.id, t.slug, t.name, t.domain, t.description",
            {"id": tradition_id},
        ).get_next()
        return Tradition(id=row[0], slug=row[1], name=row[2], domain=row[3], description=_s(row[4]))

    def get_source(self, source_id: str) -> Source:
        """Public lookup used by the document loader to validate a `Source` is
        already declared (FR6) and to read its current `content_hash` (FR23)
        before deciding whether an ingest is new, unchanged, or a replacement."""
        result = self._execute(
            "MATCH (src:Source {id: $id}) "
            "RETURN src.id, src.title, src.author, src.publication_year, src.license, src.uri, "
            "src.content_hash, src.ingested_at",
            {"id": source_id},
        )
        if not result.has_next():
            raise SourceNotFoundError(source_id)
        return self._source_from_row(result.get_next())

    def _get_source_by_id(self, source_id: str) -> Source:
        row = self._execute(
            "MATCH (src:Source {id: $id}) "
            "RETURN src.id, src.title, src.author, src.publication_year, src.license, src.uri, "
            "src.content_hash, src.ingested_at",
            {"id": source_id},
        ).get_next()
        return self._source_from_row(row)

    @staticmethod
    def _source_from_row(row: list[Any]) -> Source:
        return Source(
            id=row[0],
            title=row[1],
            author=row[2],
            publication_year=row[3],
            license=_s(row[4]),
            uri=_s(row[5]),
            content_hash=_s(row[6]),
            ingested_at=row[7],
        )

    def _get_attributes(self, interpretation_id: str) -> tuple[Attribute, ...]:
        """Tradition-scoped interpretive attributes (element, keywords, ...) — FR2."""
        return self._fetch_attributes("Interpretation", interpretation_id)

    def _get_symbol_properties(self, symbol_id: str) -> tuple[Attribute, ...]:
        """Intrinsic, tradition-independent facts about the symbol itself (alphabet
        position, numeric value, ...) — distinct from `_get_attributes` above."""
        return self._fetch_attributes("Symbol", symbol_id)

    def _fetch_attributes(self, node_label: str, node_id: str) -> tuple[Attribute, ...]:
        # node_label is one of our own fixed table names, never user input, so it's
        # safe to interpolate directly — Cypher has no parameter binding for labels.
        result = self._execute(
            f"""
            MATCH (:{node_label} {{id: $id}})-[:HAS_ATTRIBUTE]->(a:Attribute)
            RETURN a.id, a.key, a.value, a.value_type, a.position, a.retrievable
            """,
            {"id": node_id},
        )
        attributes = []
        while result.has_next():
            row = result.get_next()
            attributes.append(_attribute_from_row(row))
        attributes.sort(key=lambda attribute: attribute.position)
        return tuple(attributes)

    def _get_all_interpretation_attributes(self, symbol_id: str) -> tuple[Attribute, ...]:
        """Every attribute across *all* of a symbol's interpretations, regardless of
        tradition — used only to populate `RelationshipFact.target_semantic_facts`
        (retrieval-query enrichment, FR8), not treated as a fact about one specific
        tradition's reading. Two hops (`Symbol -> Interpretation -> Attribute`), unlike
        `_fetch_attributes`, which only handles a single direct `HAS_ATTRIBUTE` hop."""
        result = self._execute(
            """
            MATCH (:Symbol {id: $id})-[:HAS_INTERPRETATION]->(:Interpretation)-[:HAS_ATTRIBUTE]->(a:Attribute)
            RETURN a.id, a.key, a.value, a.value_type, a.position, a.retrievable
            """,
            {"id": symbol_id},
        )
        attributes = []
        while result.has_next():
            row = result.get_next()
            attributes.append(_attribute_from_row(row))
        attributes.sort(key=lambda attribute: attribute.position)
        return tuple(attributes)

    def _get_citations(self, interpretation_id: str) -> tuple[Citation, ...]:
        result = self._execute(
            "MATCH (:Interpretation {id: $id})-[r:CITES]->(src:Source) RETURN src.id, r.locator",
            {"id": interpretation_id},
        )
        citations = []
        while result.has_next():
            source_id, locator = result.get_next()
            citations.append(Citation(source=self._get_source_by_id(source_id), locator=_s(locator)))
        return tuple(citations)

    def _get_symbol_relationships(self, symbol_id: str) -> tuple[RelationshipFact, ...]:
        """This symbol's correspondences to other symbols (FR3, FR19). Targets are
        fetched shallow via `_get_symbol_by_id` (their own `.relationships` is always
        `()`, deliberately not recursed further) — but `target_semantic_facts` still
        pulls in the target's own interpretation-level attributes across every
        tradition, since that's bounded (an Interpretation has no `corresponds_to` of
        its own) and valuable for retrieval query construction (FR8)."""
        result = self._execute(
            """
            MATCH (:Symbol {id: $id})-[r:RELATES_TO]->(s2:Symbol)
            RETURN r.relationship_type, r.description, r.symmetric, r.confidence,
                   r.according_to_tradition_id, r.source_id, s2.id
            """,
            {"id": symbol_id},
        )
        relationships = []
        while result.has_next():
            (
                relationship_type,
                description,
                symmetric,
                confidence,
                according_to_tradition_id,
                source_id,
                target_symbol_id,
            ) = result.get_next()
            citation = Citation(source=self._get_source_by_id(source_id)) if source_id else None
            relationships.append(
                RelationshipFact(
                    relationship_type=relationship_type,
                    target_symbol=self._get_symbol_by_id(target_symbol_id),
                    according_to_tradition=self._get_tradition_by_id(according_to_tradition_id),
                    description=_s(description),
                    symmetric=bool(symmetric),
                    confidence=_s(confidence) or "attributed",
                    citation=citation,
                    target_semantic_facts=self._get_all_interpretation_attributes(target_symbol_id),
                )
            )
        return tuple(relationships)
