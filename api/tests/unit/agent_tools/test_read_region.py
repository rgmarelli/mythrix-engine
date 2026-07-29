# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the `read_region` tool — the one place a supplied region
identity becomes a source, a locator and a passage (FR-AU-15–FR-AU-18)."""

from conftest import FakeChatClient

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings
from mythrix.core.models import Source
from mythrix.core.vector.chunking import Chunk
from mythrix.core.vector.store import ChunkMetadata

_VERSES = [
    (0, "Genesis 21:4", "And he circumcised him the eighth day."),
    (1, "Genesis 21:5", "When he was a hundred years old."),
    (2, "Genesis 21:6", "God hath made a laughter for me."),
    (3, "Genesis 21:7", "That Sara would give suck to a son."),
    (4, "Genesis 21:8", "And the child grew and was weaned."),
]


def _ingest(stores: Stores, source_id: str = "waite") -> None:
    chunks = [
        Chunk(index=i, text=text, char_start=0, char_end=len(text), locator=locator, ordinal=i, section="Genesis 21")
        for i, locator, text in _VERSES
    ]
    stores.vector_store.add_chunks(
        chunks,
        embeddings=[[1.0, 0.0]] * len(chunks),
        metadata=ChunkMetadata(
            source_id=source_id, domain="tarot", embedding_model="fake-embed", ingested_at="2026-01-01T00:00:00+00:00"
        ),
    )


def test_read_region_fills_the_gap_between_non_adjacent_matches(
    stores: Stores,
    settings: Settings,
    tools_by_name,  # noqa: ANN001
) -> None:
    """The passage is the whole ordinal range, not the region's own
    match-carrying segments (FR-AU-17). A region matching only 21:5 and 21:8
    must still read as one contiguous passage, or the model is handed text
    with holes in it."""
    _ingest(stores)
    tools = tools_by_name(stores, settings, FakeChatClient())

    result = tools["read_region"].invoke({"region_id": "waite::1-4"})

    assert "God hath made a laughter for me." in result["text"]
    assert "That Sara would give suck to a son." in result["text"]
    assert result["text"].startswith("When he was a hundred years old.")


def test_read_region_reads_nothing_outside_the_span(
    stores: Stores,
    settings: Settings,
    tools_by_name,  # noqa: ANN001
) -> None:
    """No padding before the start or after the end (FR-AU-18), so the
    passage is exactly what the region's locator describes."""
    _ingest(stores)
    tools = tools_by_name(stores, settings, FakeChatClient())

    result = tools["read_region"].invoke({"region_id": "waite::1-3"})

    assert "eighth day" not in result["text"]
    assert "was weaned" not in result["text"]


def test_read_region_derives_the_locator_the_query_path_would_have_given(
    stores: Stores,
    settings: Settings,
    tools_by_name,  # noqa: ANN001
) -> None:
    _ingest(stores)
    tools = tools_by_name(stores, settings, FakeChatClient())

    assert tools["read_region"].invoke({"region_id": "waite::1-4"})["locator"] == "Genesis 21:5–8"
    assert tools["read_region"].invoke({"region_id": "waite::2-2"})["locator"] == "Genesis 21:6"


def test_read_region_prefers_the_citation_label_over_the_title(
    stores: Stores,
    settings: Settings,
    tools_by_name,  # noqa: ANN001
) -> None:
    """Attribution is a backend fact derived from the identity, never a value
    a consumer supplied (FR-AU-15)."""
    stores.graph_store.upsert_source(
        Source(id="drb", domain="scripture", citation_label="Douay-Rheims", title="The Holy Bible", author="")
    )
    _ingest(stores, source_id="drb")
    tools = tools_by_name(stores, settings, FakeChatClient())

    assert tools["read_region"].invoke({"region_id": "drb::1-2"})["source"] == "Douay-Rheims"


def test_read_region_falls_back_to_the_title_when_there_is_no_citation_label(
    stores: Stores,
    settings: Settings,
    tools_by_name,  # noqa: ANN001
) -> None:
    _ingest(stores)
    tools = tools_by_name(stores, settings, FakeChatClient())

    assert tools["read_region"].invoke({"region_id": "waite::1-2"})["source"] == "The Pictorial Key to the Tarot"


def test_read_region_reports_a_malformed_identity_rather_than_raising(
    stores: Stores,
    settings: Settings,
    tools_by_name,  # noqa: ANN001
) -> None:
    """A consumer-supplied identity is the one input here that can be
    arbitrary, so a bad one is a skippable result (FR-AU-16), not an
    exception that would fail the whole run."""
    tools = tools_by_name(stores, settings, FakeChatClient())

    for region_id in ("not-a-region", "waite::", "waite::1", "waite::a-b"):
        assert "error" in tools["read_region"].invoke({"region_id": region_id})


def test_read_region_reports_an_unknown_source(
    stores: Stores,
    settings: Settings,
    tools_by_name,  # noqa: ANN001
) -> None:
    tools = tools_by_name(stores, settings, FakeChatClient())

    assert "error" in tools["read_region"].invoke({"region_id": "nonexistent::1-2"})


def test_read_region_reports_a_range_holding_no_segments(
    stores: Stores,
    settings: Settings,
    tools_by_name,  # noqa: ANN001
) -> None:
    _ingest(stores)
    tools = tools_by_name(stores, settings, FakeChatClient())

    assert "error" in tools["read_region"].invoke({"region_id": "waite::900-910"})
