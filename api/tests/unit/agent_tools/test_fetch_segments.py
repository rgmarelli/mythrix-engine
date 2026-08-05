# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the `fetch_segments` tool."""

from conftest import FakeChatClient

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings
from mythrix.core.vector.chunking import Chunk
from mythrix.core.vector.store import ChunkMetadata


def test_fetch_segments_returns_the_ordinal_range(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    chunks = [
        Chunk(index=i, text=f"verse {i}", char_start=0, char_end=7, ordinal=i, section="Genesis 20") for i in range(5)
    ]
    stores.vector_store.add_chunks(
        chunks,
        embeddings=[[1.0, 0.0]] * 5,
        metadata=ChunkMetadata(
            source_id="waite", domain="tarot", embedding_model="fake-embed", ingested_at="2026-01-01T00:00:00+00:00"
        ),
    )

    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["fetch_segments"].invoke({"source_id": "waite", "start_ordinal": 1, "end_ordinal": 3})
    assert [s["ordinal"] for s in result] == [1, 2, 3]
    assert [s["text"] for s in result] == ["verse 1", "verse 2", "verse 3"]
    grounding_ids = [s["grounding_id"] for s in result]
    assert all(gid.startswith("S") and len(gid) > 1 for gid in grounding_ids)
    assert len(set(grounding_ids)) == len(grounding_ids)


def test_fetch_segments_unknown_source_returns_error_list(stores: Stores, settings: Settings, tools_by_name) -> None:  # noqa: ANN001
    tools = tools_by_name(stores, settings, FakeChatClient())
    result = tools["fetch_segments"].invoke({"source_id": "nonexistent", "start_ordinal": 0, "end_ordinal": 1})
    assert len(result) == 1
    assert "error" in result[0]
