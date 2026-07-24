"""KuzuGraphStore: deterministic, parametrized access to the Sign Graph.

Retrieval methods here are the concrete implementation of the anti-hallucination
boundary: they only ever run parametrized Cypher built from plain Python control
flow, never from LLM output or unvalidated free text (FR-RT-02). Retrieval composes
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
    ManifestationNotFoundError,
    SignNotFoundError,
    SourceNotFoundError,
    TraditionNotFoundError,
)
from mythrix.core.graph.schema import create_schema
from mythrix.core.models import (
    Citation,
    GraphFacts,
    Interpretant,
    IntersemioticInterpretant,
    Manifestation,
    Property,
    QueryDirective,
    Sign,
    SignSummary,
    Source,
    Tradition,
)


def _s(value: str | None) -> str:
    """Kùzu returns unset STRING columns as None; our models default to ""."""
    return value or ""


def _property_from_row(row: list[Any]) -> Property:
    """Shared by every query that returns `p.id, p.key, p.value, p.position` in
    that order — a row layout that recurs across `_fetch_properties`."""
    return Property(
        id=row[0],
        key=row[1],
        value=row[2],
        position=row[3] or 0,
    )


def _interpretant_from_row(row: list[Any]) -> Interpretant:
    """Shared by every query that returns `i.id, i.type, i.value, i.position,
    i.query_directive, i.query_as_token` in that order."""
    directive, as_token = row[4], row[5]
    return Interpretant(
        id=row[0],
        type=_s(row[1]) or "concept",
        value=row[2],
        position=row[3] or 0,
        query=QueryDirective(directive=directive, as_token=_s(as_token)) if directive else None,
    )


class KuzuGraphStore:
    """Owns a Kùzu database connection; exposes idempotent upserts and the
    deterministic `get_manifestation` retrieval query."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._database = kuzu.Database(str(db_path))
        self._connection = kuzu.Connection(self._database)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        existing = {row[1] for row in self._connection.execute("CALL show_tables() RETURN *")}
        if "Sign" not in existing:
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
            ON CREATE SET s.domain = $domain, s.citation_label = $citation_label, s.title = $title,
                          s.author = $author, s.publication_year = $publication_year,
                          s.license = $license, s.uri = $uri, s.description = $description,
                          s.content_hash = $content_hash, s.ingested_at = $ingested_at,
                          s.structure_scheme = $structure_scheme
            ON MATCH SET s.domain = $domain, s.citation_label = $citation_label, s.title = $title,
                         s.author = $author, s.publication_year = $publication_year,
                         s.license = $license, s.uri = $uri, s.description = $description,
                         s.content_hash = $content_hash, s.ingested_at = $ingested_at,
                         s.structure_scheme = $structure_scheme
            """,
            {
                "id": source.id,
                "domain": source.domain,
                "citation_label": source.citation_label,
                "title": source.title,
                "author": source.author,
                "publication_year": source.publication_year,
                "license": source.license,
                "uri": source.uri,
                "description": source.description,
                "content_hash": source.content_hash,
                "ingested_at": source.ingested_at,
                "structure_scheme": source.structure_scheme,
            },
        )

    def _upsert_property(self, prop: Property) -> None:
        """Shared by both sign-intrinsic and manifestation-scoped `properties` —
        a `Property` node's own fields don't depend on which kind of node points
        at it; only the `HAS_PROPERTY` edge's source differs."""
        self._execute(
            """
            MERGE (p:Property {id: $id})
            ON CREATE SET p.key = $key, p.value = $value, p.position = $position
            ON MATCH SET p.key = $key, p.value = $value, p.position = $position
            """,
            {
                "id": prop.id,
                "key": prop.key,
                "value": prop.value,
                "position": prop.position,
            },
        )

    def _upsert_interpretant(self, interpretant: Interpretant) -> None:
        self._execute(
            """
            MERGE (i:Interpretant {id: $id})
            ON CREATE SET i.type = $type, i.value = $value,
                          i.position = $position, i.query_directive = $query_directive,
                          i.query_as_token = $query_as_token
            ON MATCH SET i.type = $type, i.value = $value,
                         i.position = $position, i.query_directive = $query_directive,
                         i.query_as_token = $query_as_token
            """,
            {
                "id": interpretant.id,
                "type": interpretant.type,
                "value": interpretant.value,
                "position": interpretant.position,
                "query_directive": interpretant.query.directive if interpretant.query else None,
                "query_as_token": interpretant.query.as_token if interpretant.query else None,
            },
        )

    def upsert_sign(self, sign: Sign) -> None:
        """Writes just the Sign node and its intrinsic `properties` — no
        Manifestation. Manifestations are optional (a sign may exist purely as a
        correspondence target/anchor, e.g. a Tree of Life path never given its own
        tradition-scoped meaning); use `upsert_sign_with_manifestation` when the
        sign does have one to record.
        """
        self._execute(
            """
            MERGE (s:Sign {id: $id})
            ON CREATE SET s.slug = $slug, s.canonical_name = $canonical_name,
                          s.sign_type = $sign_type, s.semiotic_system = $semiotic_system, s.notes = $notes
            ON MATCH SET s.slug = $slug, s.canonical_name = $canonical_name,
                         s.sign_type = $sign_type, s.semiotic_system = $semiotic_system, s.notes = $notes
            """,
            {
                "id": sign.id,
                "slug": sign.slug,
                "canonical_name": sign.canonical_name,
                "sign_type": sign.sign_type,
                "semiotic_system": sign.semiotic_system,
                "notes": sign.notes,
            },
        )

        # A Property's id is derived from its key (see sign_loader.py), so
        # renaming or removing one in the YAML produces a different id — MERGE
        # alone would leave the old Property node orphaned but still linked
        # forever. Replace the full set on every load instead of merging it,
        # since each call already carries the complete current properties.
        self._execute(
            "MATCH (s:Sign {id: $id})-[e:HAS_PROPERTY]->(p:Property) DELETE e, p",
            {"id": sign.id},
        )
        for prop in sign.properties:
            self._upsert_property(prop)
            self._execute(
                """
                MATCH (s:Sign {id: $sign_id}), (p:Property {id: $property_id})
                MERGE (s)-[:HAS_PROPERTY]->(p)
                """,
                {"sign_id": sign.id, "property_id": prop.id},
            )

    def upsert_sign_with_manifestation(self, sign: Sign, manifestation: Manifestation) -> None:
        """Writes the Sign (via `upsert_sign`) plus the Manifestation (scoped to
        `manifestation.tradition`) and all of its tradition-scoped properties,
        interpretants, and citations.

        The manifestation's tradition and every cited source must already exist
        (call upsert_tradition/upsert_source first) — this method does not validate
        referential integrity; that's the structured-data loader's job (FR-SD-01, FR-SD-02).
        """
        self.upsert_sign(sign)

        self._execute(
            """
            MERGE (m:Manifestation {id: $id})
            ON CREATE SET m.sign_id = $sign_id, m.tradition_id = $tradition_id,
                          m.display_name = $display_name, m.denotation = $denotation, m.created_at = $created_at
            ON MATCH SET m.sign_id = $sign_id, m.tradition_id = $tradition_id,
                         m.display_name = $display_name, m.denotation = $denotation, m.created_at = $created_at
            """,
            {
                "id": manifestation.id,
                "sign_id": sign.id,
                "tradition_id": manifestation.tradition.id,
                "display_name": manifestation.display_name,
                "denotation": manifestation.denotation,
                "created_at": manifestation.created_at,
            },
        )

        self._execute(
            """
            MATCH (s:Sign {id: $sign_id}), (m:Manifestation {id: $manifestation_id})
            MERGE (s)-[:HAS_MANIFESTATION]->(m)
            """,
            {"sign_id": sign.id, "manifestation_id": manifestation.id},
        )
        self._execute(
            """
            MATCH (m:Manifestation {id: $manifestation_id}), (t:Tradition {id: $tradition_id})
            MERGE (m)-[:MANIFESTED_IN]->(t)
            """,
            {"manifestation_id": manifestation.id, "tradition_id": manifestation.tradition.id},
        )

        # Same reconciliation as `upsert_sign`'s properties, and for the same
        # reason: a property/interpretant's id is derived from its key/position,
        # so a renamed or removed one would otherwise leave a stale node orphaned
        # but linked.
        self._execute(
            "MATCH (m:Manifestation {id: $id})-[e:HAS_PROPERTY]->(p:Property) DELETE e, p",
            {"id": manifestation.id},
        )
        for prop in manifestation.properties:
            self._upsert_property(prop)
            self._execute(
                """
                MATCH (m:Manifestation {id: $manifestation_id}), (p:Property {id: $property_id})
                MERGE (m)-[:HAS_PROPERTY]->(p)
                """,
                {"manifestation_id": manifestation.id, "property_id": prop.id},
            )

        self._execute(
            "MATCH (m:Manifestation {id: $id})-[e:HAS_INTERPRETANT]->(i:Interpretant) DELETE e, i",
            {"id": manifestation.id},
        )
        for interpretant in manifestation.interpretants:
            self._upsert_interpretant(interpretant)
            self._execute(
                """
                MATCH (m:Manifestation {id: $manifestation_id}), (i:Interpretant {id: $interpretant_id})
                MERGE (m)-[:HAS_INTERPRETANT]->(i)
                """,
                {"manifestation_id": manifestation.id, "interpretant_id": interpretant.id},
            )

        for citation in manifestation.citations:
            self._execute(
                """
                MATCH (m:Manifestation {id: $manifestation_id}), (src:Source {id: $source_id})
                MERGE (m)-[r:CITES]->(src)
                ON CREATE SET r.locator = $locator
                ON MATCH SET r.locator = $locator
                """,
                {
                    "manifestation_id": manifestation.id,
                    "source_id": citation.source.id,
                    "locator": citation.locator,
                },
            )

    def reconcile_sign_manifestations(self, sign_id: str, current_manifestation_ids: frozenset[str]) -> None:
        """Deletes any Manifestation still linked to this sign whose id isn't
        in `current_manifestation_ids` (plus everything scoped to it — its own
        properties, interpretants, `HAS_MANIFESTATION`/`MANIFESTED_IN`/`CITES` edges).

        A Manifestation's id is derived from its sign *and* tradition slug
        (`sign_loader.py`), so renaming the tradition a manifestation belongs to
        changes the manifestation's own id — without this, the old node would be
        left orphaned but still linked forever, the same class of bug
        property/interpretant renames had (see `upsert_sign`'s reconciliation).
        Must be called once per sign with its *complete* current set, after
        every manifestation for that sign has been written this load — not
        from inside `upsert_sign_with_manifestation` itself, which only ever
        sees one manifestation at a time and would delete its own siblings.
        """
        result = self._execute(
            "MATCH (:Sign {id: $id})-[:HAS_MANIFESTATION]->(m:Manifestation) RETURN m.id",
            {"id": sign_id},
        )
        stale_ids = []
        while result.has_next():
            (manifestation_id,) = result.get_next()
            if manifestation_id not in current_manifestation_ids:
                stale_ids.append(manifestation_id)
        for manifestation_id in stale_ids:
            self._execute(
                "MATCH (m:Manifestation {id: $id})-[e:HAS_PROPERTY]->(p:Property) DELETE e, p",
                {"id": manifestation_id},
            )
            self._execute(
                "MATCH (m:Manifestation {id: $id})-[e:HAS_INTERPRETANT]->(i:Interpretant) DELETE e, i",
                {"id": manifestation_id},
            )
            self._execute("MATCH (m:Manifestation {id: $id}) DETACH DELETE m", {"id": manifestation_id})

    def upsert_intersemiotic_interpretant(
        self,
        *,
        from_sign_id: str,
        to_sign_id: str,
        relationship: str,
        according_to_id: str,
        description: str = "",
        symmetric: bool = False,
        confidence: str = "attributed",
        source_id: str = "",
    ) -> None:
        """Idempotent per (from, to, relationship, according_to_id) — re-running
        with the same identity updates description/confidence/etc. in place; a
        *different* according_to_id adds a new, independent claim rather than
        overwriting the first (FR-DM-03; verified in
        tests/unit/test_kuzu_multi_edge_risk.py).

        Connects `Sign -> Sign` directly, not through either endpoint's
        `Manifestation` — a sign with zero manifestations can still be a valid
        `to_sign_id`/`from_sign_id`.
        """
        self._execute(
            """
            MATCH (a:Sign {id: $from_id}), (b:Sign {id: $to_id})
            MERGE (a)-[r:INTERSEMIOTIC {
                relationship: $relationship,
                according_to_id: $according_to_id
            }]->(b)
            ON CREATE SET r.description = $description, r.symmetric = $symmetric,
                          r.confidence = $confidence, r.source_id = $source_id
            ON MATCH SET r.description = $description, r.symmetric = $symmetric,
                         r.confidence = $confidence, r.source_id = $source_id
            """,
            {
                "from_id": from_sign_id,
                "to_id": to_sign_id,
                "relationship": relationship,
                "according_to_id": according_to_id,
                "description": description,
                "symmetric": symmetric,
                "confidence": confidence,
                "source_id": source_id,
            },
        )

    # -- Retrieval -----------------------------------------------------------------

    def get_manifestation(self, sign_slug: str, tradition_slug: str) -> GraphFacts:
        """Deterministic, parametrized retrieval of one sign's manifestation
        within one tradition (FR-RT-01, FR-RT-02) — never generated from LLM output."""
        sign = self._get_sign_by_slug(sign_slug)
        tradition = self._get_tradition_by_slug(tradition_slug)

        result = self._execute(
            """
            MATCH (s:Sign {id: $sign_id})-[:HAS_MANIFESTATION]->(m:Manifestation)
                  -[:MANIFESTED_IN]->(t:Tradition {id: $tradition_id})
            RETURN m.id, m.display_name, m.denotation, m.created_at
            """,
            {"sign_id": sign.id, "tradition_id": tradition.id},
        )
        if not result.has_next():
            raise ManifestationNotFoundError(sign_slug, tradition_slug)
        manifestation_id, display_name, denotation, created_at = result.get_next()

        manifestation = Manifestation(
            id=manifestation_id,
            sign_id=sign.id,
            tradition=tradition,
            display_name=display_name,
            denotation=_s(denotation),
            properties=self._get_manifestation_properties(manifestation_id),
            interpretants=self._get_interpretants(manifestation_id),
            citations=self._get_citations(manifestation_id),
            created_at=created_at,
        )
        # Intersemiotic interpretants belong to the sign, not this specific
        # manifestation (see Sign.intersemiotic_interpretants docstring) —
        # populated here via model_copy since _get_sign_by_slug/_get_sign_by_id
        # deliberately return relationship targets shallow, to avoid unbounded
        # recursion through IntersemioticInterpretant.target_sign.
        sign = sign.model_copy(
            update={"intersemiotic_interpretants": self._get_sign_intersemiotic_interpretants(sign.id)}
        )
        return GraphFacts(sign=sign, manifestation=manifestation)

    def list_traditions(self) -> tuple[Tradition, ...]:
        """Every declared `Tradition`, for a web/API picker (`specs/interfaces/web-viewer.md`
        FR-WEB-01)."""
        result = self._execute(
            "MATCH (t:Tradition) RETURN t.id, t.slug, t.name, t.domain, t.description ORDER BY t.slug", {}
        )
        traditions = []
        while result.has_next():
            row = result.get_next()
            traditions.append(Tradition(id=row[0], slug=row[1], name=row[2], domain=row[3], description=_s(row[4])))
        return tuple(traditions)

    def list_semiotic_systems(self) -> tuple[str, ...]:
        """Every distinct `semiotic_system` that has at least one manifested
        sign, ordered — the top-level scope a picker (or the agent's
        `list_semiotic_systems` tool, `specs/interfaces/agent.md` FR-AG-03) offers before
        narrowing to traditions/signs. Consistent with `list_signs`: a system
        whose only signs have zero manifestations is never offered, so it can
        never lead to a dead scope."""
        result = self._execute(
            """
            MATCH (s:Sign)-[:HAS_MANIFESTATION]->(:Manifestation)
            RETURN DISTINCT s.semiotic_system ORDER BY s.semiotic_system
            """,
            {},
        )
        systems = []
        while result.has_next():
            (semiotic_system,) = result.get_next()
            systems.append(semiotic_system)
        return tuple(systems)

    def list_signs(self) -> tuple[SignSummary, ...]:
        """Every sign with at least one manifestation, one row per
        (sign, tradition) grouped by sign slug — a sign with zero
        manifestations (FR-DM-05) is never returned, so a web/API picker can
        only ever offer a sign/tradition pair `get_manifestation` will
        actually resolve (`specs/interfaces/web-viewer.md` FR-WEB-01)."""
        result = self._execute(
            """
            MATCH (s:Sign)-[:HAS_MANIFESTATION]->(:Manifestation)-[:MANIFESTED_IN]->(t:Tradition)
            RETURN s.slug, s.canonical_name, s.sign_type, s.semiotic_system, t.slug
            ORDER BY s.slug
            """,
            {},
        )
        tradition_slugs_by_sign: dict[str, list[str]] = {}
        sign_row_by_slug: dict[str, tuple[str, str, str]] = {}
        while result.has_next():
            slug, canonical_name, sign_type, semiotic_system, tradition_slug = result.get_next()
            tradition_slugs_by_sign.setdefault(slug, []).append(tradition_slug)
            sign_row_by_slug.setdefault(slug, (canonical_name, sign_type, semiotic_system))
        return tuple(
            SignSummary(
                slug=slug,
                canonical_name=sign_row_by_slug[slug][0],
                sign_type=sign_row_by_slug[slug][1],
                semiotic_system=sign_row_by_slug[slug][2],
                tradition_slugs=tuple(tradition_slugs_by_sign[slug]),
            )
            for slug in tradition_slugs_by_sign
        )

    # -- Internal lookups -----------------------------------------------------------------

    def _get_sign_by_slug(self, slug: str) -> Sign:
        result = self._execute(
            "MATCH (s:Sign {slug: $slug}) RETURN s.id, s.slug, s.canonical_name, s.sign_type, s.semiotic_system, s.notes",
            {"slug": slug},
        )
        if not result.has_next():
            raise SignNotFoundError(slug)
        row = result.get_next()
        return Sign(
            id=row[0],
            slug=row[1],
            canonical_name=row[2],
            sign_type=row[3],
            semiotic_system=_s(row[4]),
            notes=_s(row[5]),
            properties=self._get_sign_properties(row[0]),
        )

    def _get_sign_by_id(self, sign_id: str) -> Sign:
        row = self._execute(
            "MATCH (s:Sign {id: $id}) RETURN s.id, s.slug, s.canonical_name, s.sign_type, s.semiotic_system, s.notes",
            {"id": sign_id},
        ).get_next()
        return Sign(
            id=row[0],
            slug=row[1],
            canonical_name=row[2],
            sign_type=row[3],
            semiotic_system=_s(row[4]),
            notes=_s(row[5]),
            properties=self._get_sign_properties(row[0]),
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
        already declared (FR-CO-01) and to read its current `content_hash` (FR-CO-04)
        before deciding whether an ingest is new, unchanged, or a replacement."""
        result = self._execute(
            "MATCH (src:Source {id: $id}) "
            "RETURN src.id, src.domain, src.citation_label, src.title, src.author, src.publication_year, "
            "src.license, src.uri, src.description, src.content_hash, src.ingested_at, src.structure_scheme",
            {"id": source_id},
        )
        if not result.has_next():
            raise SourceNotFoundError(source_id)
        return self._source_from_row(result.get_next())

    def _get_source_by_id(self, source_id: str) -> Source:
        row = self._execute(
            "MATCH (src:Source {id: $id}) "
            "RETURN src.id, src.domain, src.citation_label, src.title, src.author, src.publication_year, "
            "src.license, src.uri, src.description, src.content_hash, src.ingested_at, src.structure_scheme",
            {"id": source_id},
        ).get_next()
        return self._source_from_row(row)

    @staticmethod
    def _source_from_row(row: list[Any]) -> Source:
        return Source(
            id=row[0],
            domain=_s(row[1]),
            citation_label=_s(row[2]),
            title=row[3],
            author=row[4],
            publication_year=row[5],
            license=_s(row[6]),
            uri=_s(row[7]),
            description=_s(row[8]),
            content_hash=_s(row[9]),
            ingested_at=row[10],
            structure_scheme=_s(row[11]),
        )

    def _get_interpretants(self, manifestation_id: str) -> tuple[Interpretant, ...]:
        """Tradition-scoped interpretants (concepts, keywords, exact-value facts, ...) — FR-DM-02."""
        result = self._execute(
            """
            MATCH (:Manifestation {id: $id})-[:HAS_INTERPRETANT]->(i:Interpretant)
            RETURN i.id, i.type, i.value, i.position, i.query_directive, i.query_as_token
            """,
            {"id": manifestation_id},
        )
        interpretants = []
        while result.has_next():
            interpretants.append(_interpretant_from_row(result.get_next()))
        interpretants.sort(key=lambda interpretant: interpretant.position)
        return tuple(interpretants)

    def _get_sign_properties(self, sign_id: str) -> tuple[Property, ...]:
        """Intrinsic, tradition-independent facts about the sign itself (alphabet
        position, numeric value, ...) — distinct from `_get_manifestation_properties`."""
        return self._fetch_properties("Sign", sign_id)

    def _get_manifestation_properties(self, manifestation_id: str) -> tuple[Property, ...]:
        """Structural facts specific to one tradition's rendering of the sign
        (e.g. a card's deck position in one specific deck) — distinct from
        `_get_sign_properties`."""
        return self._fetch_properties("Manifestation", manifestation_id)

    def _fetch_properties(self, node_label: str, node_id: str) -> tuple[Property, ...]:
        # node_label is one of our own fixed table names, never user input, so it's
        # safe to interpolate directly — Cypher has no parameter binding for labels.
        result = self._execute(
            f"""
            MATCH (:{node_label} {{id: $id}})-[:HAS_PROPERTY]->(p:Property)
            RETURN p.id, p.key, p.value, p.position
            """,
            {"id": node_id},
        )
        properties = []
        while result.has_next():
            properties.append(_property_from_row(result.get_next()))
        properties.sort(key=lambda prop: prop.position)
        return tuple(properties)

    def _get_all_manifestation_interpretants(self, sign_id: str) -> tuple[Interpretant, ...]:
        """Every interpretant across *all* of a sign's manifestations, regardless of
        tradition — used only to populate `IntersemioticInterpretant.target_interpretants`
        (retrieval-query enrichment, FR-CO-03), not treated as a fact about one specific
        tradition's reading. Never fetches properties, at either scope — properties are
        never used to build retrieval query text (FR-CO-03, FR-DM-04). Two hops
        (`Sign -> Manifestation -> Interpretant`), unlike `_fetch_properties`/`_get_interpretants`,
        which only handle a single direct hop."""
        result = self._execute(
            """
            MATCH (:Sign {id: $id})-[:HAS_MANIFESTATION]->(:Manifestation)-[:HAS_INTERPRETANT]->(i:Interpretant)
            RETURN i.id, i.type, i.value, i.position, i.query_directive, i.query_as_token
            """,
            {"id": sign_id},
        )
        interpretants = []
        while result.has_next():
            interpretants.append(_interpretant_from_row(result.get_next()))
        interpretants.sort(key=lambda interpretant: interpretant.position)
        return tuple(interpretants)

    def _get_citations(self, manifestation_id: str) -> tuple[Citation, ...]:
        result = self._execute(
            "MATCH (:Manifestation {id: $id})-[r:CITES]->(src:Source) RETURN src.id, r.locator",
            {"id": manifestation_id},
        )
        citations = []
        while result.has_next():
            source_id, locator = result.get_next()
            citations.append(Citation(source=self._get_source_by_id(source_id), locator=_s(locator)))
        return tuple(citations)

    def _get_sign_intersemiotic_interpretants(self, sign_id: str) -> tuple[IntersemioticInterpretant, ...]:
        """This sign's correspondences to other signs (FR-DM-03, FR-SD-04). Targets are
        fetched shallow via `_get_sign_by_id` (their own `.intersemiotic_interpretants`
        is always `()`, deliberately not recursed further) — but `target_interpretants`
        still pulls in the target's own manifestation-level interpretants across every
        tradition, since that's bounded (a Manifestation has no intersemiotic
        interpretants of its own) and valuable for retrieval query construction (FR-CO-03)."""
        result = self._execute(
            """
            MATCH (:Sign {id: $id})-[r:INTERSEMIOTIC]->(s2:Sign)
            RETURN r.relationship, r.description, r.symmetric, r.confidence,
                   r.according_to_id, r.source_id, s2.id
            """,
            {"id": sign_id},
        )
        interpretants = []
        while result.has_next():
            (
                relationship,
                description,
                symmetric,
                confidence,
                according_to_id,
                source_id,
                target_sign_id,
            ) = result.get_next()
            citation = Citation(source=self._get_source_by_id(source_id)) if source_id else None
            interpretants.append(
                IntersemioticInterpretant(
                    relationship=relationship,
                    target_sign=self._get_sign_by_id(target_sign_id),
                    according_to=self._get_tradition_by_id(according_to_id),
                    description=_s(description),
                    symmetric=bool(symmetric),
                    confidence=_s(confidence) or "attributed",
                    citation=citation,
                    target_interpretants=self._get_all_manifestation_interpretants(target_sign_id),
                )
            )
        return tuple(interpretants)
