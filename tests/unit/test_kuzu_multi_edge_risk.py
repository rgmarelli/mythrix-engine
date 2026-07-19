"""T8 — blocking risk check (see tasks.md, plan.md Risks).

The alternative/competing-claims design for RELATES_TO (FR3) — e.g. two attribution
systems assigning a tarot card to different Hebrew letters — depends on Kùzu allowing
multiple edges of the same rel table between the *same* node pair, not just between
different pairs. This test pins that assumption against the exact pinned kuzu version:
if a future version bump silently starts deduplicating or rejecting parallel edges,
this test fails loudly instead of corrupting data silently.

RELATES_TO connects Symbol -> Symbol directly (not Interpretation -> Interpretation —
see schema.py's module docstring for why), so this test creates bare Symbol nodes.
"""

from pathlib import Path

import kuzu

from mythrix.core.graph.schema import create_schema


def test_kuzu_allows_multiple_relates_to_edges_between_same_node_pair(tmp_path: Path) -> None:
    database = kuzu.Database(str(tmp_path / "graph.kuzu"))
    connection = kuzu.Connection(database)
    create_schema(connection)

    connection.execute(
        "CREATE (:Symbol {id: $id, slug: $slug, canonical_name: $cn, symbol_type: $st, notes: ''})",
        parameters={"id": "the-tower", "slug": "the-tower", "cn": "The Tower", "st": "major-arcana"},
    )
    connection.execute(
        "CREATE (:Symbol {id: $id, slug: $slug, canonical_name: $cn, symbol_type: $st, notes: ''})",
        parameters={"id": "hebrew-letter-peh", "slug": "hebrew-letter-peh", "cn": "Peh", "st": "hebrew-letter"},
    )

    for according_to in ("golden-dawn-kabbalah", "pre-golden-dawn-correspondence"):
        connection.execute(
            """
            MATCH (a:Symbol {id: $from_id}), (b:Symbol {id: $to_id})
            CREATE (a)-[:RELATES_TO {
                relationship_type: $relationship_type,
                description: $description,
                symmetric: false,
                confidence: 'attributed',
                according_to_tradition_id: $according_to,
                source_id: ''
            }]->(b)
            """,
            parameters={
                "from_id": "the-tower",
                "to_id": "hebrew-letter-peh",
                "relationship_type": "corresponds_to_letter",
                "description": f"Attribution per {according_to}.",
                "according_to": according_to,
            },
        )

    result = connection.execute(
        """
        MATCH (a:Symbol {id: $from_id})-[r:RELATES_TO]->(b:Symbol {id: $to_id})
        RETURN r.according_to_tradition_id
        """,
        parameters={"from_id": "the-tower", "to_id": "hebrew-letter-peh"},
    )
    attributions = sorted(row[0] for row in result)

    assert attributions == ["golden-dawn-kabbalah", "pre-golden-dawn-correspondence"]
