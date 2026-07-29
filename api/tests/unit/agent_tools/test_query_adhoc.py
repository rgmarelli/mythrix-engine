"""Unit tests for the `query_adhoc` tool — the node-only ad-hoc retrieval step
(FR-DS-11, FR-DS-13, FR-DS-29)."""

import pytest
from conftest import FakeChatClient

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings
from mythrix.core.vector.chunking import Chunk
from mythrix.core.vector.store import ChromaVectorStore, ChunkMetadata


@pytest.fixture
def corpus(vector_store: ChromaVectorStore) -> None:
    """Four passages far enough apart in ordinal to roll up into four separate
    regions at `region_window_size=3`."""
    chunks = [
        Chunk(
            index=i,
            text=f"There were a hundred fish, full of laughter, in passage {i}.",
            char_start=0,
            char_end=10,
            ordinal=ordinal,
            section="",
        )
        for i, ordinal in enumerate((0, 10, 20, 30))
    ]
    vector_store.add_chunks(
        chunks,
        embeddings=[[1.0, 0.0] for _ in chunks],
        metadata=ChunkMetadata(
            source_id="waite", domain="tarot", embedding_model="fake-embed", ingested_at="2026-01-01T00:00:00+00:00"
        ),
    )


def test_query_adhoc_returns_ranked_regions_and_the_matched_count(
    stores: Stores, settings: Settings, tools_by_name, corpus: None
) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())

    result = tools["query_adhoc"].invoke({"terms": [{"value": "laughter"}], "limit": 8})

    assert result["matched_count"] == 4
    assert len(result["regions"]) == 4
    assert all("region_id" in region and "locator" in region for region in result["regions"])


def test_query_adhoc_truncates_from_the_top_of_the_ranking(
    stores: Stores, settings: Settings, tools_by_name, corpus: None
) -> None:  # noqa: ANN001
    """FR-DS-12/FR-DS-13: the bound is applied by head-truncation, and the
    matched count still reports everything retrieval returned."""
    tools = tools_by_name(stores, settings, FakeChatClient())

    full = tools["query_adhoc"].invoke({"terms": [{"value": "laughter"}], "limit": 8})
    limited = tools["query_adhoc"].invoke({"terms": [{"value": "laughter"}], "limit": 2})

    assert limited["matched_count"] == 4
    assert limited["regions"] == full["regions"][:2]


def test_query_adhoc_carries_no_passage_text(stores: Stores, settings: Settings, tools_by_name, corpus: None) -> None:  # noqa: ANN001
    """FR-DS-29: this result is fabricated into conversation history, and the
    passages are re-read by structural coordinate anyway."""
    tools = tools_by_name(stores, settings, FakeChatClient())

    result = tools["query_adhoc"].invoke({"terms": [{"value": "laughter"}], "limit": 8})

    assert all("segments" not in region for region in result["regions"])
    assert "full of laughter" not in str(result)


def test_query_adhoc_honors_term_directives(stores: Stores, settings: Settings, tools_by_name, corpus: None) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())

    result = tools["query_adhoc"].invoke(
        {"terms": [{"value": "laughter"}, {"value": "hundred", "directive": "exact"}], "limit": 8}
    )

    kinds = {match["interpretant"]: match["kind"] for match in result["regions"][0]["matches"]}
    assert kinds == {"laughter": "concept", "hundred": "exact"}


def test_query_adhoc_with_no_terms_returns_an_error(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    """`AdhocQueryValidationError` is a `MythrixError`, so it becomes a
    structured result rather than crashing the node (FR-AG-11)."""
    tools = tools_by_name(stores, settings, FakeChatClient())

    result = tools["query_adhoc"].invoke({"terms": [], "limit": 8})

    assert "error" in result
