"""Unit tests for `agent/tools.py::build_tools` — the seven read-only tools,
each a thin wrapper over an existing service function. Real
`KuzuGraphStore`/`ChromaVectorStore` against `tmp_path`, a fake embedder —
mirrors `tests/unit/test_query_service.py`; no running Ollama needed."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mythrix.agent.tools import build_tools
from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings
from mythrix.core.errors import ModelUnavailableError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import Citation, Interpretant, Manifestation, Sign, Source, Tradition
from mythrix.core.vector.chunking import Chunk
from mythrix.core.vector.store import ChromaVectorStore, ChunkMetadata

RIDER_WAITE = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")
MARSEILLE = Tradition(id="marseille", slug="marseille", name="Tarot de Marseille", domain="tarot")
GOLDEN_DAWN = Tradition(
    id="golden-dawn-kabbalah", slug="golden-dawn-kabbalah", name="Golden Dawn Kabbalah", domain="kabbalah"
)
CREATED_AT = datetime(2026, 1, 1, tzinfo=UTC)


class FakeEmbedder:
    model_name = "fake-embed"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class FakeChatClient:
    generation_model = "fake-model"

    def __init__(self, response: str = "a summary") -> None:
        self._response = response

    def invoke(self, prompt: str) -> str:
        return self._response


class RaisingChatClient:
    generation_model = "fake-model"

    def invoke(self, prompt: str) -> str:
        raise ModelUnavailableError(self.generation_model)


@pytest.fixture
def graph_store(tmp_path: Path) -> KuzuGraphStore:
    store = KuzuGraphStore(tmp_path / "graph.kuzu")
    for tradition in (RIDER_WAITE, MARSEILLE, GOLDEN_DAWN):
        store.upsert_tradition(tradition)
    waite_source = Source(id="waite", domain="tarot", title="The Pictorial Key to the Tarot", author="A. E. Waite")
    store.upsert_source(waite_source)

    the_tower = Sign(
        id="the-tower", slug="the-tower", canonical_name="The Tower", sign_type="major-arcana", semiotic_system="tarot"
    )
    tower_manifestation = Manifestation(
        id="the-tower::rider-waite",
        sign_id="the-tower",
        tradition=RIDER_WAITE,
        display_name="The Tower",
        denotation="Sudden upheaval; the collapse of false structures.",
        interpretants=(Interpretant(id="interp-element", type="element", value="Fire"),),
        created_at=CREATED_AT,
    )
    store.upsert_sign_with_manifestation(the_tower, tower_manifestation)

    the_magician = Sign(
        id="the-magician",
        slug="the-magician",
        canonical_name="The Magician",
        sign_type="major-arcana",
        semiotic_system="tarot",
    )
    magician_rw = Manifestation(
        id="the-magician::rider-waite",
        sign_id="the-magician",
        tradition=RIDER_WAITE,
        display_name="The Magician",
        denotation="Willed manifestation.",
        interpretants=(Interpretant(id="interp-magician-power", type="concept", value="willpower"),),
        citations=(Citation(source=waite_source, locator="p. 71"),),
        created_at=CREATED_AT,
    )
    store.upsert_sign_with_manifestation(the_magician, magician_rw)
    magician_marseille = Manifestation(
        id="the-magician::marseille",
        sign_id="the-magician",
        tradition=MARSEILLE,
        display_name="Le Bateleur",
        created_at=CREATED_AT,
    )
    store.upsert_sign_with_manifestation(the_magician, magician_marseille)

    peh = Sign(
        id="hebrew-letter-peh",
        slug="hebrew-letter-peh",
        canonical_name="Peh",
        sign_type="hebrew-letter",
        semiotic_system="hebrew_alef_bet",
    )
    peh_manifestation = Manifestation(
        id="hebrew-letter-peh::golden-dawn-kabbalah",
        sign_id="hebrew-letter-peh",
        tradition=GOLDEN_DAWN,
        display_name="Peh",
        created_at=CREATED_AT,
    )
    store.upsert_sign_with_manifestation(peh, peh_manifestation)
    return store


@pytest.fixture
def vector_store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(tmp_path / "chroma")


@pytest.fixture
def stores(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> Stores:
    return Stores(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())


@pytest.fixture
def settings() -> Settings:
    return Settings(
        retrieval_top_k=6,
        retrieval_match_pool_size=30,
        merge_top_k=6,
        retrieval_min_score=0.0,
        region_window_size=3,
        region_min_interpretants=1,
    )


def _tools_by_name(stores: Stores, settings: Settings, chat_client) -> dict:  # noqa: ANN001
    return {t.name: t for t in build_tools(stores, settings, chat_client)}


def test_build_tools_returns_exactly_the_seven_read_only_tools(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    assert set(tools) == {
        "list_semiotic_systems",
        "list_traditions",
        "list_signs",
        "get_sign",
        "query_sign",
        "fetch_segments",
        "summarize_passage",
    }


def test_list_semiotic_systems(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["list_semiotic_systems"].invoke({})
    assert result == ["hebrew_alef_bet", "tarot"]


def test_list_traditions_unscoped(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["list_traditions"].invoke({})
    assert {t["slug"] for t in result} == {"rider-waite", "marseille", "golden-dawn-kabbalah"}


def test_list_traditions_scoped_by_semiotic_system(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["list_traditions"].invoke({"semiotic_system": "hebrew_alef_bet"})
    assert {t["slug"] for t in result} == {"golden-dawn-kabbalah"}


def test_list_signs_scoped_by_semiotic_system(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["list_signs"].invoke({"semiotic_system": "tarot"})
    assert {s["slug"] for s in result} == {"the-tower", "the-magician"}
    the_magician = next(s for s in result if s["slug"] == "the-magician")
    assert set(the_magician["traditions"]) == {"rider-waite", "marseille"}


def test_list_signs_unscoped_includes_every_system(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["list_signs"].invoke({})
    assert {s["slug"] for s in result} == {"the-tower", "the-magician", "hebrew-letter-peh"}


def test_get_sign_auto_resolves_single_tradition_sign(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "the-tower"})
    assert result["sign"] == "The Tower"
    assert result["tradition"] == "Rider-Waite-Smith"
    assert result["interpretants"] == [{"type": "element", "value": "Fire"}]


def test_get_sign_needs_tradition_for_multi_tradition_sign(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "the-magician"})
    assert result == {
        "needs_tradition": True,
        "sign": "The Magician",
        "traditions": ["rider-waite", "marseille"],
    }


def test_get_sign_with_tradition_returns_facts_and_citations(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "the-magician", "tradition": "rider-waite"})
    assert result["display_name"] == "The Magician"
    assert result["citations"] == [{"source": "The Pictorial Key to the Tarot", "locator": "p. 71"}]


def test_get_sign_unknown_slug_returns_error(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "nonexistent"})
    assert "error" in result


def test_get_sign_resolves_by_canonical_name_not_only_slug(stores: Stores, settings: Settings) -> None:
    """A real failure mode: the model derives `sign` from the user's own
    wording ("The Magician") before any tool has surfaced the slug
    ("the-magician") — the spec's own `get_sign` example uses exactly this
    display-name phrasing, so slug-only matching must not be the only path."""
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "The Magician", "tradition": "rider-waite"})
    assert result["display_name"] == "The Magician"
    assert "error" not in result


def test_get_sign_name_match_is_case_and_whitespace_insensitive(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "  the magician  ", "tradition": "rider-waite"})
    assert result["display_name"] == "The Magician"


def test_get_sign_unknown_tradition_returns_error(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["get_sign"].invoke({"sign": "the-tower", "tradition": "nonexistent"})
    assert "error" in result


def test_query_sign_returns_regions_dict(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["query_sign"].invoke({"sign": "the-tower", "tradition": "rider-waite"})
    assert result == {"regions": []}


def test_query_sign_resolves_by_canonical_name_not_only_slug(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["query_sign"].invoke({"sign": "The Tower", "tradition": "rider-waite"})
    assert result == {"regions": []}
    assert "error" not in result


def test_query_sign_unknown_sign_returns_error(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["query_sign"].invoke({"sign": "nonexistent", "tradition": "rider-waite"})
    assert "error" in result


def test_fetch_segments_returns_the_ordinal_range(stores: Stores, settings: Settings) -> None:
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

    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["fetch_segments"].invoke({"source_id": "waite", "start_ordinal": 1, "end_ordinal": 3})
    assert [s["ordinal"] for s in result] == [1, 2, 3]
    assert [s["text"] for s in result] == ["verse 1", "verse 2", "verse 3"]


def test_fetch_segments_unknown_source_returns_error_list(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient())
    result = tools["fetch_segments"].invoke({"source_id": "nonexistent", "start_ordinal": 0, "end_ordinal": 1})
    assert len(result) == 1
    assert "error" in result[0]


def test_summarize_passage_returns_the_chat_client_response(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, FakeChatClient("Fire dominates."))
    result = tools["summarize_passage"].invoke({"passage_text": "some text", "concepts": ["Fire"]})
    assert result == {"summary": "Fire dominates."}


def test_summarize_passage_unreachable_model_returns_error(stores: Stores, settings: Settings) -> None:
    tools = _tools_by_name(stores, settings, RaisingChatClient())
    result = tools["summarize_passage"].invoke({"passage_text": "some text", "concepts": ["Fire"]})
    assert "error" in result
