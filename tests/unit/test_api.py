"""Unit tests for `mythrix.api`: `fastapi.testclient.TestClient` against
`create_app()`, `Stores` injected via `app.dependency_overrides[get_stores]`
— no `with TestClient(...) as client:` (that would trigger the real
`lifespan`, building real stores against the default `.mythrix/` paths),
real `KuzuGraphStore`/`ChromaVectorStore` against `tmp_path`, a fake
embedder. Mirrors `tests/unit/test_cli_query.py`'s fixture pattern."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from mythrix.agent.graph import compile_agent_graph
from mythrix.agent.sessions import SessionStore
from mythrix.api.app import create_app
from mythrix.api.dependencies import get_agent_graph, get_agent_sessions, get_chat_client, get_stores
from mythrix.core.bootstrap import Stores
from mythrix.core.errors import ModelUnavailableError, SignNotFoundError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import Interpretant, Manifestation, Sign, Source, Tradition
from mythrix.core.vector.chunking import Chunk
from mythrix.core.vector.store import ChromaVectorStore, ChunkMetadata

RIDER_WAITE = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")


class FakeChatClient:
    generation_model = "fake-chat"

    def __init__(self, response: str = "a summary") -> None:
        self.response = response
        self.last_prompt: str | None = None

    def invoke(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


class UnavailableChatClient:
    generation_model = "fake-chat"

    def invoke(self, prompt: str) -> str:  # noqa: ARG002
        raise ModelUnavailableError(self.generation_model)


class FakeEmbedder:
    model_name = "fake-embed"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class UnreachableEmbedder:
    model_name = "fake-embed"

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise ModelUnavailableError(self.model_name)


@pytest.fixture
def graph_store(tmp_path: Path) -> KuzuGraphStore:
    store = KuzuGraphStore(tmp_path / "graph.kuzu")
    store.upsert_tradition(RIDER_WAITE)
    store.upsert_source(
        Source(id="waite", domain="tarot", title="The Pictorial Key to the Tarot", author="A. E. Waite")
    )
    the_tower = Sign(
        id="the-tower",
        slug="the-tower",
        canonical_name="The Tower",
        sign_type="major-arcana",
        semiotic_system="tarot",
    )
    manifestation = Manifestation(
        id="the-tower::rider-waite",
        sign_id="the-tower",
        tradition=RIDER_WAITE,
        display_name="The Tower",
        denotation="Sudden upheaval; the collapse of false structures.",
        interpretants=(Interpretant(id="interp-element", type="element", value="Fire"),),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store.upsert_sign_with_manifestation(the_tower, manifestation)
    # A correspondence-only sign with zero manifestations — must not appear from /api/symbols.
    store.upsert_sign(
        Sign(
            id="path-anchor",
            slug="path-anchor",
            canonical_name="Path Anchor",
            sign_type="tree-of-life-path",
            semiotic_system="hebrew_alef_bet",
        )
    )
    return store


@pytest.fixture
def vector_store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(tmp_path / "chroma")


def _client(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, embedder=None) -> TestClient:  # noqa: ANN001
    app = create_app()
    app.dependency_overrides[get_stores] = lambda: Stores(
        graph_store=graph_store, vector_store=vector_store, embedder=embedder or FakeEmbedder()
    )
    return TestClient(app)


def test_list_traditions(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    client = _client(graph_store, vector_store)
    response = client.get("/api/traditions")
    assert response.status_code == 200
    assert [t["slug"] for t in response.json()] == ["rider-waite"]


def test_list_symbols_excludes_signs_with_no_manifestation(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    client = _client(graph_store, vector_store)
    response = client.get("/api/symbols")
    assert response.status_code == 200
    body = response.json()
    assert [s["slug"] for s in body] == ["the-tower"]
    assert body[0]["semiotic_system"] == "tarot"
    assert body[0]["tradition_slugs"] == ["rider-waite"]


def test_query_returns_facets_and_regions(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    client = _client(graph_store, vector_store)
    response = client.get("/api/query", params={"symbol": "the-tower", "tradition": "rider-waite"})
    assert response.status_code == 200
    body = response.json()
    assert body == {"facets": {"sources": [], "interpretants": []}, "regions": []}


def test_query_unknown_symbol_returns_404(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    client = _client(graph_store, vector_store)
    response = client.get("/api/query", params={"symbol": "nonexistent", "tradition": "rider-waite"})
    assert response.status_code == 404
    assert "detail" in response.json()


def test_query_unreachable_embedder_returns_502(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    client = _client(graph_store, vector_store, embedder=UnreachableEmbedder())
    response = client.get("/api/query", params={"symbol": "the-tower", "tradition": "rider-waite"})
    assert response.status_code == 502
    assert "detail" in response.json()


def test_query_returns_a_region_converging_on_every_matching_interpretant(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    """A region matched by two interpretants appears once, with both
    recorded in `matches`, each anchored to the segment it hit (FR17) —
    the concrete case `convergence-rollup-retrieval` exists for. Both of
    the-sun's interpretants embed identically here (`FakeEmbedder` returns a
    fixed vector for any text), and the corpus has exactly one chunk, so that
    chunk is the top hit for both."""
    graph_store.upsert_sign_with_manifestation(
        Sign(
            id="the-sun",
            slug="the-sun",
            canonical_name="The Sun",
            sign_type="major-arcana",
            semiotic_system="tarot",
        ),
        Manifestation(
            id="the-sun::rider-waite",
            sign_id="the-sun",
            tradition=RIDER_WAITE,
            display_name="The Sun",
            interpretants=(
                Interpretant(id="interp-a", type="concept", value="joy"),
                Interpretant(id="interp-b", type="concept", value="vitality"),
            ),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )
    vector_store.add_chunks(
        [Chunk(index=0, text="Rejoice, for the light has come.", char_start=0, char_end=33, locator="Ch. 1")],
        embeddings=[[1.0, 0.0]],
        metadata=ChunkMetadata(
            source_id="waite", domain="tarot", embedding_model="fake-embed", ingested_at="2026-01-01T00:00:00Z"
        ),
    )

    client = _client(graph_store, vector_store)
    response = client.get("/api/query", params={"symbol": "the-sun", "tradition": "rider-waite"})

    assert response.status_code == 200
    body = response.json()
    assert len(body["regions"]) == 1
    region = body["regions"][0]
    assert region["locator"] == "Ch. 1"
    assert len(region["segments"]) == 1
    assert region["segments"][0]["text"] == "Rejoice, for the light has come."
    assert {m["interpretant"] for m in region["matches"]} == {"joy", "vitality"}
    assert all(m["segment_ordinal"] == region["segments"][0]["ordinal"] for m in region["matches"])
    assert region["convergence_count"] == 2
    assert body["facets"]["sources"] == [{"id": "waite", "label": "The Pictorial Key to the Tarot", "count": 1}]
    interpretant_counts = {f["value"]: f["count"] for f in body["facets"]["interpretants"]}
    assert interpretant_counts == {"joy": 1, "vitality": 1}


def test_query_min_score_param_overrides_the_settings_default(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    """`min_score` is a per-request override (checked with `is None`, not
    truthiness, since `0.0` is a meaningful explicit value): an identical
    query/chunk embedding here always scores `1.0`, so a `min_score` above
    that excludes it even though it clears `Settings.retrieval_min_score`'s
    own default (`0.6`)."""
    vector_store.add_chunks(
        [Chunk(index=0, text="The Tower represents sudden upheaval.", char_start=0, char_end=38)],
        embeddings=[[1.0, 0.0]],
        metadata=ChunkMetadata(
            source_id="waite", domain="tarot", embedding_model="fake-embed", ingested_at="2026-01-01T00:00:00Z"
        ),
    )
    client = _client(graph_store, vector_store)

    response = client.get("/api/query", params={"symbol": "the-tower", "tradition": "rider-waite", "min_score": 1.5})

    assert response.status_code == 200
    assert response.json()["regions"] == []


def test_segments_returns_the_ordinal_range(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    chunks = [
        Chunk(index=i, text=f"verse {i}", char_start=0, char_end=7, ordinal=i, section="Genesis 20") for i in range(5)
    ]
    vector_store.add_chunks(
        chunks,
        embeddings=[[1.0, 0.0]] * 5,
        metadata=ChunkMetadata(
            source_id="waite", domain="tarot", embedding_model="fake-embed", ingested_at="2026-01-01T00:00:00Z"
        ),
    )
    client = _client(graph_store, vector_store)

    response = client.get("/api/segments", params={"source_id": "waite", "start_ordinal": 1, "end_ordinal": 3})

    assert response.status_code == 200
    body = response.json()
    assert [s["ordinal"] for s in body] == [1, 2, 3]
    assert [s["text"] for s in body] == ["verse 1", "verse 2", "verse 3"]
    assert all(s["section"] == "Genesis 20" for s in body)


def test_segments_unknown_source_returns_404(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    client = _client(graph_store, vector_store)

    response = client.get("/api/segments", params={"source_id": "nonexistent", "start_ordinal": 0, "end_ordinal": 1})

    assert response.status_code == 404
    assert "detail" in response.json()


def test_reload_symbols_loads_yaml_into_the_running_graph_store(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, tmp_path: Path
) -> None:
    """Proves the endpoint writes through the *same* `graph_store` instance
    the running app was already using (dependency-injected here, just as
    `Stores` is injected once at real startup) rather than opening a second
    connection — the scenario `/api/reload-symbols` exists to support."""
    data_root = tmp_path / "data"
    (data_root / "traditions").mkdir(parents=True)
    (data_root / "traditions" / "rider-waite.yaml").write_text(
        'tradition:\n  name: "Rider-Waite-Smith"\n  domain: tarot\n', encoding="utf-8"
    )
    (data_root / "signs").mkdir(parents=True)
    (data_root / "signs" / "the-fool.yaml").write_text(
        """
semiotic_system: tarot_cards
sign:
  name: "The Fool"
  type: major-arcana
  manifestations:
    - tradition: rider-waite
      display_name: "The Fool"
""",
        encoding="utf-8",
    )
    client = _client(graph_store, vector_store)

    response = client.post("/api/reload-symbols", params={"path": str(data_root)})

    assert response.status_code == 200
    assert response.json() == {
        "traditions": 1,
        "sources": 0,
        "signs": 1,
        "manifestations": 1,
        "intersemiotic_interpretants": 0,
    }
    the_fool = graph_store.get_manifestation("the-fool", "rider-waite")
    assert the_fool.manifestation.display_name == "The Fool"


def test_reload_symbols_invalid_data_returns_422_and_writes_nothing(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, tmp_path: Path
) -> None:
    data_root = tmp_path / "data"
    (data_root / "traditions").mkdir(parents=True)
    (data_root / "traditions" / "rider-waite.yaml").write_text(
        'tradition:\n  name: "Rider-Waite-Smith"\n  domain: tarot\n', encoding="utf-8"
    )
    (data_root / "signs").mkdir(parents=True)
    (data_root / "signs" / "the-fool.yaml").write_text(
        """
semiotic_system: tarot_cards
sign:
  name: "The Fool"
  type: major-arcana
  manifestations:
    - tradition: rider-waite
      display_name: "The Fool"
      cites: "Some Nonexistent Source, p. 1"
""",
        encoding="utf-8",
    )
    client = _client(graph_store, vector_store)

    response = client.post("/api/reload-symbols", params={"path": str(data_root)})

    assert response.status_code == 422
    assert "detail" in response.json()
    with pytest.raises(SignNotFoundError):
        graph_store.get_manifestation("the-fool", "rider-waite")


def test_summarize_passage_returns_chat_client_response(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    client = _client(graph_store, vector_store)
    fake_chat_client = FakeChatClient(response="Sudden upheaval, focused on collapse.")
    client.app.dependency_overrides[get_chat_client] = lambda: fake_chat_client

    response = client.post("/api/summarize", json={"passage_text": "The tower falls.", "concepts": ["collapse"]})

    assert response.status_code == 200
    assert response.json() == {"summary": "Sudden upheaval, focused on collapse."}
    assert "collapse" in fake_chat_client.last_prompt
    assert "The tower falls." in fake_chat_client.last_prompt


def test_summarize_passage_unavailable_model_is_502(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    client = _client(graph_store, vector_store)
    client.app.dependency_overrides[get_chat_client] = lambda: UnavailableChatClient()

    response = client.post("/api/summarize", json={"passage_text": "The tower falls.", "concepts": ["collapse"]})

    assert response.status_code == 502
    assert "detail" in response.json()


@tool("get_symbol")
def _fake_get_symbol(symbol: str, tradition: str | None = None) -> dict:
    """Fake get_symbol for `/api/agent` integration tests."""
    if tradition is None:
        return {"needs_tradition": True, "symbol": "The Magician", "traditions": ["rider-waite", "marseille"]}
    return {
        "sign": "The Magician",
        "semiotic_system": "tarot",
        "tradition": tradition,
        "citations": [{"source": "Waite", "locator": "p. 1"}],
    }


class _ScriptedLLM:
    def __init__(self, script: list[AIMessage]) -> None:
        self.script = list(script)
        self.calls = 0

    def invoke(self, messages: list) -> AIMessage:  # noqa: ARG002
        response = self.script[self.calls]
        self.calls += 1
        return response


def _agent_client(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, script: list[AIMessage]) -> TestClient:
    client = _client(graph_store, vector_store)
    client.app.dependency_overrides[get_agent_sessions] = lambda: SessionStore()
    client.app.dependency_overrides[get_agent_graph] = lambda: compile_agent_graph(
        _ScriptedLLM(script), [_fake_get_symbol]
    )
    return client


def test_agent_turn_returns_grounded_reply_context_and_cards(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    script = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "get_symbol", "args": {"symbol": "The Magician", "tradition": "rider-waite"}, "id": "c1"}
            ],
        ),
        AIMessage(content="The Magician represents willpower [G1]."),
    ]
    client = _agent_client(graph_store, vector_store, script)

    response = client.post(
        "/api/agent",
        json={
            "session_id": "s1",
            "message": "tell me about the magician in rider-waite",
            "ui_selection": {},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "[G1]" not in body["reply_text"]
    assert "willpower" in body["reply_text"]
    assert body["context"]["sign"] == "The Magician"
    assert body["context"]["tradition"] == "rider-waite"
    assert len(body["cards"]) == 1
    assert body["cards"][0]["source_label"] == "Waite"
    assert body["instructions"] == []


def test_agent_turn_reset_on_hotspot_change(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    script = [AIMessage(content="Hi there.")]
    client = _agent_client(graph_store, vector_store, script)
    sessions = SessionStore()
    client.app.dependency_overrides[get_agent_sessions] = lambda: sessions
    client.app.dependency_overrides[get_agent_graph] = lambda: compile_agent_graph(
        _ScriptedLLM(script + [AIMessage(content="Hi again.")]), [_fake_get_symbol]
    )

    first = client.post(
        "/api/agent",
        json={"session_id": "s1", "message": "hi", "ui_selection": {"region_id": "waite::0-1"}},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/agent",
        json={"session_id": "s1", "message": "hi again", "ui_selection": {"region_id": "waite::2-3"}},
    )
    assert second.status_code == 200
    assert second.json()["thread_reset"] is True


def test_agent_turn_ambiguous_tradition_asks_with_no_second_model_call(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    llm = _ScriptedLLM(
        [AIMessage(content="", tool_calls=[{"name": "get_symbol", "args": {"symbol": "The Magician"}, "id": "c1"}])]
    )
    client = _client(graph_store, vector_store)
    client.app.dependency_overrides[get_agent_sessions] = lambda: SessionStore()
    client.app.dependency_overrides[get_agent_graph] = lambda: compile_agent_graph(llm, [_fake_get_symbol])

    response = client.post(
        "/api/agent",
        json={"session_id": "s1", "message": "tell me about the magician", "ui_selection": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert "rider-waite" in body["reply_text"]
    assert "marseille" in body["reply_text"]
    assert body["cards"] == []
    assert llm.calls == 1


def test_agent_turn_unavailable_model_is_502(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    client = _client(graph_store, vector_store)
    client.app.dependency_overrides[get_agent_sessions] = lambda: SessionStore()

    def _raise_unavailable():
        raise ModelUnavailableError("fake-agent-model")

    client.app.dependency_overrides[get_agent_graph] = _raise_unavailable

    response = client.post(
        "/api/agent",
        json={"session_id": "s1", "message": "hi", "ui_selection": {}},
    )

    assert response.status_code == 502
    assert "detail" in response.json()
