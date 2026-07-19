"""Kùzu DDL for the Symbol Graph — the single source of truth for its schema.

Domain-agnostic by construction: every table here is generic (Symbol, Tradition,
Interpretation, Attribute, Source, and their relationships). No domain-specific
column or table belongs here — see tests/unit/test_domain_agnosticism.py.

`Interpretation` is the key join entity: "this Symbol as understood within this
Tradition." Tradition-specific *meaning* (display name, summary, attributes, citations)
hangs off `Interpretation`, never off the bare `Symbol` — this is what keeps distinct
traditions from ever collapsing into one merged meaning (FR2).

`RELATES_TO` (correspondences between symbols, e.g. a tarot card to a Hebrew letter)
connects `Symbol -> Symbol` directly, not `Interpretation -> Interpretation`. A
correspondence claim's attribution lives entirely in its `according_to_tradition_id`
property — tying the edge to one *specific* interpretation of each endpoint as well
would be redundant scoping, and would block a symbol with zero interpretations from
ever participating in a correspondence (FR3, and the "interpretations are optional"
requirement it must support).

Kùzu is pre-1.0 and its DDL syntax has changed release-to-release, so this module is
validated against the exact `kuzu` version pinned in pyproject.toml (see
tests/unit/test_graph_schema.py) — bumping that pin requires re-verifying this DDL.
"""

from __future__ import annotations

NODE_TABLE_DDL: tuple[str, ...] = (
    """
    CREATE NODE TABLE Symbol(
        id STRING,
        slug STRING,
        canonical_name STRING,
        symbol_type STRING,
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
    CREATE NODE TABLE Interpretation(
        id STRING,
        symbol_id STRING,
        tradition_id STRING,
        display_name STRING,
        summary STRING,
        created_at TIMESTAMP,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE NODE TABLE Attribute(
        id STRING,
        key STRING,
        value STRING,
        value_type STRING,
        position INT64,
        retrievable BOOLEAN,
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
        title STRING,
        author STRING,
        publication_year INT64,
        license STRING,
        uri STRING,
        content_hash STRING,
        ingested_at TIMESTAMP,
        PRIMARY KEY (id)
    )
    """,
)

REL_TABLE_DDL: tuple[str, ...] = (
    "CREATE REL TABLE HAS_INTERPRETATION(FROM Symbol TO Interpretation)",
    "CREATE REL TABLE INTERPRETED_IN(FROM Interpretation TO Tradition)",
    # Symbol->Attribute is for intrinsic, tradition-independent facts (e.g. a Hebrew
    # letter's alphabet position or numeric value). Interpretation->Attribute is for
    # tradition-dependent interpretive claims (e.g. element, keywords). Keeping both
    # pairs on one rel table lets a single query pattern disambiguate by node type.
    "CREATE REL TABLE HAS_ATTRIBUTE(FROM Symbol TO Attribute, FROM Interpretation TO Attribute)",
    "CREATE REL TABLE CITES(FROM Interpretation TO Source, locator STRING)",
    """
    CREATE REL TABLE RELATES_TO(
        FROM Symbol TO Symbol,
        relationship_type STRING,
        description STRING,
        symmetric BOOLEAN,
        confidence STRING,
        according_to_tradition_id STRING,
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
