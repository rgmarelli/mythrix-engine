"""Unit tests for `mythrix.api`: `fastapi.testclient.TestClient` against
`create_app()`, `Stores` injected via `app.dependency_overrides[get_stores]`
— no `with TestClient(...) as client:` (that would trigger the real
`lifespan`, building real stores against the default `.mythrix/` paths),
real `KuzuGraphStore`/`ChromaVectorStore` against `tmp_path`, a fake
embedder. Mirrors `tests/unit/test_cli_query.py`'s fixture pattern."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from graph_helpers import compile_graph
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from mythrix.agent.commands.adhoc import execute_query_instruction
from mythrix.agent.sessions import SessionStore
from mythrix.api.app import create_app
from mythrix.api.dependencies import get_agent_graph, get_agent_sessions, get_stores
from mythrix.core.bootstrap import Stores
from mythrix.core.errors import ModelUnavailableError, SignNotFoundError
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import AdhocTerm, Interpretant, Manifestation, Sign, Source, Tradition
from mythrix.core.vector.chunking import Chunk
from mythrix.core.vector.store import ChromaVectorStore, ChunkMetadata

RIDER_WAITE = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")


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
    # A correspondence-only sign with zero manifestations — must not appear from /api/signs.
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


def test_list_signs_excludes_signs_with_no_manifestation(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    client = _client(graph_store, vector_store)
    response = client.get("/api/signs")
    assert response.status_code == 200
    body = response.json()
    assert [s["slug"] for s in body] == ["the-tower"]
    assert body[0]["semiotic_system"] == "tarot"
    assert body[0]["tradition_slugs"] == ["rider-waite"]


def test_query_returns_facets_and_regions(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    client = _client(graph_store, vector_store)
    response = client.get("/api/query", params={"sign": "the-tower", "tradition": "rider-waite"})
    assert response.status_code == 200
    body = response.json()
    assert body == {"facets": {"sources": [], "interpretants": []}, "regions": []}


def test_query_unknown_sign_returns_404(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    client = _client(graph_store, vector_store)
    response = client.get("/api/query", params={"sign": "nonexistent", "tradition": "rider-waite"})
    assert response.status_code == 404
    assert "detail" in response.json()


def test_query_unreachable_embedder_returns_502(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    client = _client(graph_store, vector_store, embedder=UnreachableEmbedder())
    response = client.get("/api/query", params={"sign": "the-tower", "tradition": "rider-waite"})
    assert response.status_code == 502
    assert "detail" in response.json()


def test_adhoc_query_returns_facets_and_regions(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    client = _client(graph_store, vector_store)
    response = client.request("QUERY", "/api/query/adhoc", json={"terms": [{"value": "laughter", "directive": None}]})
    assert response.status_code == 200
    body = response.json()
    assert body == {"facets": {"sources": [], "interpretants": []}, "regions": []}


def test_adhoc_query_matches_a_segment_via_exact_directive(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    chunks = [
        Chunk(index=0, text="A hundred fish swim beneath Pisces.", char_start=0, char_end=10, ordinal=0, section="")
    ]
    vector_store.add_chunks(
        chunks,
        embeddings=[[1.0, 0.0]],
        metadata=ChunkMetadata(
            source_id="waite", domain="tarot", embedding_model="fake-embed", ingested_at="2026-01-01T00:00:00+00:00"
        ),
    )
    client = _client(graph_store, vector_store)
    response = client.request("QUERY", "/api/query/adhoc", json={"terms": [{"value": "hundred", "directive": "exact"}]})
    assert response.status_code == 200
    body = response.json()
    assert len(body["regions"]) == 1
    assert body["regions"][0]["matches"][0]["kind"] == "exact"


def test_adhoc_query_empty_terms_returns_422(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    client = _client(graph_store, vector_store)
    response = client.request("QUERY", "/api/query/adhoc", json={"terms": []})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_adhoc_query_is_a_read_not_a_post(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    """The endpoint answers QUERY (RFC 10008) and nothing else — an ad-hoc query
    creates and modifies nothing, and the capabilities document publishes that
    method to every consumer (agent-capabilities.md FR-CAP-16)."""
    client = _client(graph_store, vector_store)
    response = client.post("/api/query/adhoc", json={"terms": [{"value": "laughter", "directive": None}]})
    assert response.status_code == 405


def test_execute_query_instruction_payload_is_a_valid_request_body(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    """FR-AQ-22/FR-CAP-12: the `payload` body mode sends an instruction's
    payload unmodified, so the agent's instruction and this endpoint's request
    body are one shape. Pinned here because nothing else would fail if they
    drifted apart."""
    instruction = execute_query_instruction(
        (AdhocTerm(value="laughter"), AdhocTerm(value="hundred", directive="exact"))
    )
    client = _client(graph_store, vector_store)

    response = client.request("QUERY", "/api/query/adhoc", json=instruction["payload"])

    assert response.status_code == 200
    assert set(response.json()) == {"facets", "regions"}


def test_agent_capabilities_declares_commands_and_bindings(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    client = _client(graph_store, vector_store)
    body = client.get("/api/agent/capabilities").json()

    commands = {command["name"]: command for command in body["commands"]}
    assert commands["/clear"]["handled_by"] == "client"
    assert commands["/query"]["handled_by"] == "server"
    assert commands["/query-confirm"]["listed"] is False

    bindings = {instruction["type"]: instruction["binding"] for instruction in body["instructions"]}
    assert bindings["confirm_query"] is None
    assert bindings["execute_query"] == {
        "method": "QUERY",
        "path": "/api/query/adhoc",
        "body": "payload",
        "result": "regions",
    }


def test_declared_execute_query_binding_reaches_a_real_endpoint(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    """Follows the manifest the way a consumer does — method and path taken
    from the document, body taken from the instruction — so a binding that
    names a route this build does not serve fails here rather than in a
    browser."""
    client = _client(graph_store, vector_store)
    binding = next(
        instruction["binding"]
        for instruction in client.get("/api/agent/capabilities").json()["instructions"]
        if instruction["type"] == "execute_query"
    )
    payload = execute_query_instruction((AdhocTerm(value="laughter"),))["payload"]

    response = client.request(binding["method"], binding["path"], json=payload)

    assert response.status_code == 200


def test_query_returns_a_region_converging_on_every_matching_interpretant(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    """A region matched by two interpretants appears once, with both
    recorded in `matches`, each anchored to the segment it hit (FR-RK-09) —
    the concrete case region rollup exists for. Both of
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
    response = client.get("/api/query", params={"sign": "the-sun", "tradition": "rider-waite"})

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

    response = client.get("/api/query", params={"sign": "the-tower", "tradition": "rider-waite", "min_score": 1.5})

    assert response.status_code == 200
    assert response.json()["regions"] == []


def test_query_logs_params_duration_count_and_score_range(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, caplog: pytest.LogCaptureFixture
) -> None:
    vector_store.add_chunks(
        [Chunk(index=0, text="The Tower represents sudden upheaval.", char_start=0, char_end=38)],
        embeddings=[[1.0, 0.0]],
        metadata=ChunkMetadata(
            source_id="waite", domain="tarot", embedding_model="fake-embed", ingested_at="2026-01-01T00:00:00Z"
        ),
    )
    client = _client(graph_store, vector_store)

    with caplog.at_level(logging.INFO, logger="mythrix.api.routes"):
        response = client.get("/api/query", params={"sign": "the-tower", "tradition": "rider-waite"})

    assert response.status_code == 200
    query_lines = [record.getMessage() for record in caplog.records if record.getMessage().startswith("query:")]
    assert len(query_lines) == 1
    line = query_lines[0]
    assert "sign=the-tower" in line
    assert "tradition=rider-waite" in line
    assert "regions=1" in line
    assert "score_range=n/a" not in line


def test_query_with_no_results_logs_score_range_as_na(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, caplog: pytest.LogCaptureFixture
) -> None:
    client = _client(graph_store, vector_store)

    with caplog.at_level(logging.INFO, logger="mythrix.api.routes"):
        response = client.get("/api/query", params={"sign": "the-tower", "tradition": "rider-waite"})

    assert response.status_code == 200
    query_lines = [record.getMessage() for record in caplog.records if record.getMessage().startswith("query:")]
    assert len(query_lines) == 1
    assert "regions=0" in query_lines[0]
    assert "score_range=n/a" in query_lines[0]


def test_query_unknown_sign_logs_failure_and_still_returns_404(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, caplog: pytest.LogCaptureFixture
) -> None:
    client = _client(graph_store, vector_store)

    with caplog.at_level(logging.INFO, logger="mythrix.api.routes"):
        response = client.get("/api/query", params={"sign": "nonexistent", "tradition": "rider-waite"})

    assert response.status_code == 404
    messages = [record.getMessage() for record in caplog.records]
    assert any(m.startswith("query failed:") for m in messages)


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


def test_reload_signs_loads_yaml_into_the_running_graph_store(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore, tmp_path: Path
) -> None:
    """Proves the endpoint writes through the *same* `graph_store` instance
    the running app was already using (dependency-injected here, just as
    `Stores` is injected once at real startup) rather than opening a second
    connection — the scenario `/api/reload-signs` exists to support."""
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

    response = client.post("/api/reload-signs", params={"path": str(data_root)})

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


def test_reload_signs_invalid_data_returns_422_and_writes_nothing(
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

    response = client.post("/api/reload-signs", params={"path": str(data_root)})

    assert response.status_code == 422
    assert "detail" in response.json()
    with pytest.raises(SignNotFoundError):
        graph_store.get_manifestation("the-fool", "rider-waite")


@tool("get_sign")
def _fake_get_sign(sign: str, tradition: str | None = None) -> dict:
    """Fake get_sign for `/api/agent` integration tests."""
    if tradition is None:
        return {"needs_tradition": True, "sign": "The Magician", "traditions": ["rider-waite", "marseille"]}
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
    client.app.dependency_overrides[get_agent_graph] = lambda: compile_graph(_ScriptedLLM(script), [_fake_get_sign])
    return client


def test_agent_turn_returns_grounded_reply_and_context(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    script = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_sign", "args": {"sign": "The Magician", "tradition": "rider-waite"}, "id": "c1"}],
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
    assert body["instructions"] == []


def test_agent_turn_reset_on_hotspot_change(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    script = [AIMessage(content="Hi there.")]
    client = _agent_client(graph_store, vector_store, script)
    sessions = SessionStore()
    client.app.dependency_overrides[get_agent_sessions] = lambda: sessions
    client.app.dependency_overrides[get_agent_graph] = lambda: compile_graph(
        _ScriptedLLM(script + [AIMessage(content="Hi again.")]), [_fake_get_sign]
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
        [AIMessage(content="", tool_calls=[{"name": "get_sign", "args": {"sign": "The Magician"}, "id": "c1"}])]
    )
    client = _client(graph_store, vector_store)
    client.app.dependency_overrides[get_agent_sessions] = lambda: SessionStore()
    client.app.dependency_overrides[get_agent_graph] = lambda: compile_graph(llm, [_fake_get_sign])

    response = client.post(
        "/api/agent",
        json={"session_id": "s1", "message": "tell me about the magician", "ui_selection": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert "rider-waite" in body["reply_text"]
    assert "marseille" in body["reply_text"]
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


def test_agent_turn_is_delivered_as_ndjson(graph_store: KuzuGraphStore, vector_store: ChromaVectorStore) -> None:
    """FR-AU-22: every turn uses the streaming shape, so there is one turn
    transport rather than two that must be kept equal (ADR-015)."""
    client = _agent_client(graph_store, vector_store, [AIMessage(content="Hi there.")])

    response = client.post("/api/agent", json={"session_id": "s1", "message": "hi", "ui_selection": {}})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in response.text.splitlines() if line]
    assert [line["event"] for line in lines] == ["turn"]


def test_an_augmentation_run_streams_one_line_per_region_then_the_turn(
    graph_store: KuzuGraphStore, vector_store: ChromaVectorStore
) -> None:
    """FR-AU-23: the per-region results reach the consumer as they land, on
    the same connection, ahead of the consolidation."""

    @tool
    def read_region(region_id: str) -> dict:
        """Fake read_region."""
        return {
            "region_id": region_id,
            "source": "Douay-Rheims",
            "source_id": "waite",
            "locator": "Genesis 21:6",
            "text": "God hath made a laughter for me.",
        }

    @tool
    def augment_passage(passage_text: str, focus: str) -> dict:
        """Fake augment_passage."""
        return {"augmentation": "a reading"}

    @tool
    def consolidate_augmentations(focus: str, augmentations: list[dict]) -> dict:
        """Fake consolidate_augmentations."""
        return {"consolidation": "Joy recurs [R1]."}

    client = _agent_client(graph_store, vector_store, [])
    sessions = SessionStore()
    client.app.dependency_overrides[get_agent_sessions] = lambda: sessions
    client.app.dependency_overrides[get_agent_graph] = lambda: compile_graph(
        _ScriptedLLM([]),
        [_fake_get_sign],
        node_tools=[read_region, augment_passage, consolidate_augmentations],
    )

    plan = client.post(
        "/api/agent",
        json={
            "session_id": "s1",
            "message": "/augment where is joy",
            "ui_selection": {},
            "visible_regions": ["waite::0-1"],
        },
    )
    assert plan.status_code == 200
    augmentation_id = sessions.get_or_create("s1").pending_augmentation.id

    run = client.post(
        "/api/agent",
        json={"session_id": "s1", "message": f"/augment-confirm {augmentation_id}", "ui_selection": {}},
    )

    lines = [json.loads(line) for line in run.text.splitlines() if line]
    assert [line["event"] for line in lines] == ["message", "instruction", "turn"]
    assert lines[1]["instruction"]["payload"]["region_id"] == "waite::0-1"
    assert lines[2]["reply_text"].startswith("Joy recurs [R1].")
