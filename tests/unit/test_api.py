"""Unit tests for `mythrix.api`: `fastapi.testclient.TestClient` against
`create_app()`, `Stores` injected via `app.dependency_overrides[get_stores]`
— no `with TestClient(...) as client:` (that would trigger the real
`lifespan`, building real stores against the default `.mythrix/` paths),
real `KuzuGraphStore`/`ChromaVectorStore` against `tmp_path`, a fake
embedder. Mirrors `tests/unit/test_cli_query.py`'s fixture pattern."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mythrix.api.app import create_app
from mythrix.api.dependencies import get_chat_client, get_stores
from mythrix.core.bootstrap import Stores
from mythrix.core.errors import ModelUnavailableError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import Attribute, Interpretation, Source, Symbol, Tradition
from mythrix.core.vector.store import ChromaVectorStore

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
    store.upsert_source(Source(id="waite", title="The Pictorial Key to the Tarot", author="A. E. Waite"))
    the_tower = Symbol(id="the-tower", slug="the-tower", canonical_name="The Tower", symbol_type="major-arcana")
    interpretation = Interpretation(
        id="the-tower::rider-waite",
        symbol_id="the-tower",
        tradition=RIDER_WAITE,
        display_name="The Tower",
        summary="Sudden upheaval; the collapse of false structures.",
        attributes=(Attribute(id="attr-element", key="element", value="Fire"),),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store.upsert_symbol_with_interpretation(the_tower, interpretation)
    # A correspondence-only symbol with zero interpretations — must not appear from /api/symbols.
    store.upsert_symbol(
        Symbol(id="path-anchor", slug="path-anchor", canonical_name="Path Anchor", symbol_type="tree-of-life-path")
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


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        if not block:
            continue
        event_line, data_line = block.split("\n", 1)
        events.append((event_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: "))))
    return events


def test_list_traditions(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    client = _client(graph_store, vector_store)
    response = client.get("/api/traditions")
    assert response.status_code == 200
    assert [t["slug"] for t in response.json()] == ["rider-waite"]


def test_list_symbols_excludes_symbols_with_no_interpretation(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    client = _client(graph_store, vector_store)
    response = client.get("/api/symbols")
    assert response.status_code == 200
    body = response.json()
    assert [s["slug"] for s in body] == ["the-tower"]
    assert body[0]["tradition_slugs"] == ["rider-waite"]


def test_query_streams_graph_facts_then_done(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    client = _client(graph_store, vector_store)
    with client.stream("GET", "/api/query", params={"symbol": "the-tower", "tradition": "rider-waite"}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(response.read().decode())

    assert events[0][0] == "graph_facts"
    assert events[0][1]["symbol"]["slug"] == "the-tower"
    assert events[-1] == ("done", {})
    assert all(event_type in {"concept_candidates", "pair_candidates"} for event_type, _ in events[1:-1])


def test_query_unknown_symbol_is_a_pre_stream_404(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    client = _client(graph_store, vector_store)
    response = client.get("/api/query", params={"symbol": "nonexistent", "tradition": "rider-waite"})
    assert response.status_code == 404
    assert "detail" in response.json()


def test_query_unreachable_embedder_is_a_mid_stream_error_event(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    client = _client(graph_store, vector_store, embedder=UnreachableEmbedder())
    with client.stream("GET", "/api/query", params={"symbol": "the-tower", "tradition": "rider-waite"}) as response:
        assert response.status_code == 200
        events = _parse_sse(response.read().decode())

    assert events[0][0] == "graph_facts"
    assert events[-1][0] == "error"
    assert "detail" in events[-1][1]
    assert not any(event_type == "done" for event_type, _ in events)


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
