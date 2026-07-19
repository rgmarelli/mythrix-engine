"""Verify the Kùzu DDL in core.graph.schema applies cleanly and creates every table.

Uses the real, pinned kuzu package against a throwaway on-disk database — no external
daemon required (Kùzu is embedded), so this runs in the regular unit suite.
"""

from pathlib import Path

import kuzu

from mythrix.core.graph.schema import ALL_DDL, NODE_TABLE_DDL, REL_TABLE_DDL, create_schema

EXPECTED_NODE_TABLES = {"Symbol", "Tradition", "Interpretation", "Attribute", "Source"}
EXPECTED_REL_TABLES = {"HAS_INTERPRETATION", "INTERPRETED_IN", "HAS_ATTRIBUTE", "CITES", "RELATES_TO"}


def test_schema_creates_all_expected_tables(tmp_path: Path) -> None:
    database = kuzu.Database(str(tmp_path / "graph.kuzu"))
    connection = kuzu.Connection(database)

    create_schema(connection)

    result = connection.execute("CALL show_tables() RETURN *")
    tables = {row[1]: row[2] for row in result}

    assert tables.keys() >= EXPECTED_NODE_TABLES
    assert tables.keys() >= EXPECTED_REL_TABLES
    for name in EXPECTED_NODE_TABLES:
        assert tables[name] == "NODE"
    for name in EXPECTED_REL_TABLES:
        assert tables[name] == "REL"


def test_all_ddl_is_included_in_node_and_rel_tuples() -> None:
    assert set(ALL_DDL) == set(NODE_TABLE_DDL) | set(REL_TABLE_DDL)
    assert len(NODE_TABLE_DDL) == len(EXPECTED_NODE_TABLES)
    assert len(REL_TABLE_DDL) == len(EXPECTED_REL_TABLES)


def test_has_attribute_spans_both_symbol_and_interpretation(tmp_path: Path) -> None:
    """HAS_ATTRIBUTE must connect from both Symbol (intrinsic properties) and
    Interpretation (tradition-scoped attributes) — this is what lets Samekh's
    alphabet position live on the symbol while its meaning stays tradition-scoped."""
    database = kuzu.Database(str(tmp_path / "graph.kuzu"))
    connection = kuzu.Connection(database)
    create_schema(connection)

    pairs = {(row[0], row[1]) for row in connection.execute("CALL show_connection('HAS_ATTRIBUTE') RETURN *")}

    assert pairs == {("Symbol", "Attribute"), ("Interpretation", "Attribute")}
