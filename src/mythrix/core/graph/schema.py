"""Kùzu DDL for the Sign Graph — the single source of truth for its schema.

Domain-agnostic by construction: every table here is generic (Sign, Tradition,
Manifestation, Property, Interpretant, Source, and their relationships). No
domain-specific column or table belongs here — see tests/unit/test_domain_agnosticism.py.

`Manifestation` is the key join entity: "this Sign as understood within this
Tradition." Tradition-specific *meaning* (display name, denotation, properties,
interpretants, citations) hangs off `Manifestation`, never off the bare `Sign` —
this is what keeps distinct traditions from ever collapsing into one merged
meaning (FR2).

`INTERSEMIOTIC` (correspondences between signs, e.g. a tarot card to a Hebrew
letter) connects `Sign -> Sign` directly, not `Manifestation -> Manifestation`.
A correspondence claim's attribution lives entirely in its `according_to_id`
property — tying the edge to one *specific* manifestation of each endpoint as
well would be redundant scoping, and would block a sign with zero manifestations
from ever participating in a correspondence (FR3, and the "manifestations are
optional" requirement it must support).

`Property` and `Interpretant` are separate node tables: a property is never used
to build retrieval query text regardless of scope (FR8, FR21), while an
interpretant always is unless it carries a `query_directive` (FR28) — the two
roles have different columns and no shared upsert path, unlike the earlier
single `Attribute` table this schema replaces.

Kùzu is pre-1.0 and its DDL syntax has changed release-to-release, so this module is
validated against the exact `kuzu` version pinned in pyproject.toml (see
tests/unit/test_graph_schema.py) — bumping that pin requires re-verifying this DDL.
"""

from __future__ import annotations

NODE_TABLE_DDL: tuple[str, ...] = (
    """
    CREATE NODE TABLE Sign(
        id STRING,
        slug STRING,
        canonical_name STRING,
        sign_type STRING,
        semiotic_system STRING,
        notes STRING,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE NODE TABLE Tradition(
        id STRING,
        slug STRING,
        name STRING,
        domain STRING,
        description STRING,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE NODE TABLE Manifestation(
        id STRING,
        sign_id STRING,
        tradition_id STRING,
        display_name STRING,
        denotation STRING,
        created_at TIMESTAMP,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE NODE TABLE Property(
        id STRING,
        key STRING,
        value STRING,
        position INT64,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE NODE TABLE Interpretant(
        id STRING,
        type STRING,
        value STRING,
        position INT64,
        query_directive STRING,
        query_as_token STRING,
        PRIMARY KEY (id)
    )
    """,
    # `content_hash`/`ingested_at` are written by the document loader, not authored
    # in a Source YAML file — they record what's currently ingested for this
    # source so re-running the loader can no-op on an unchanged file or replace
    # chunks on a changed one, rather than accumulating duplicates (FR23).
    """
    CREATE NODE TABLE Source(
        id STRING,
        domain STRING,
        citation_label STRING,
        title STRING,
        author STRING,
        publication_year INT64,
        license STRING,
        uri STRING,
        description STRING,
        content_hash STRING,
        ingested_at TIMESTAMP,
        structure_scheme STRING,
        PRIMARY KEY (id)
    )
    """,
)

REL_TABLE_DDL: tuple[str, ...] = (
    "CREATE REL TABLE HAS_MANIFESTATION(FROM Sign TO Manifestation)",
    "CREATE REL TABLE MANIFESTED_IN(FROM Manifestation TO Tradition)",
    # Sign->Property is for intrinsic, tradition-independent facts (e.g. a Hebrew
    # letter's alphabet position or numeric value). Manifestation->Property is for
    # tradition-specific structural facts (e.g. a card's deck number in one
    # specific deck). Keeping both pairs on one rel table lets a single query
    # pattern disambiguate by node type.
    "CREATE REL TABLE HAS_PROPERTY(FROM Sign TO Property, FROM Manifestation TO Property)",
    "CREATE REL TABLE HAS_INTERPRETANT(FROM Manifestation TO Interpretant)",
    "CREATE REL TABLE CITES(FROM Manifestation TO Source, locator STRING)",
    """
    CREATE REL TABLE INTERSEMIOTIC(
        FROM Sign TO Sign,
        relationship STRING,
        description STRING,
        symmetric BOOLEAN,
        confidence STRING,
        according_to_id STRING,
        source_id STRING
    )
    """,
)

ALL_DDL: tuple[str, ...] = NODE_TABLE_DDL + REL_TABLE_DDL


def create_schema(connection: object) -> None:
    """Create every node and rel table on a fresh Kùzu connection.

    Args:
        connection: A `kuzu.Connection` open against an empty database.
    """
    for statement in ALL_DDL:
        connection.execute(statement)  # type: ignore[attr-defined]
