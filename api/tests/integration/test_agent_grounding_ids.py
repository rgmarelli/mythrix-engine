# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Real-Ollama, real-graph/vector-store coverage for ADR-022's tool-owned
opaque grounding ids — opt-in (`@pytest.mark.requires_ollama`), not run as
part of the default `pytest tests/unit` suite; run explicitly with `pytest
tests/integration -m requires_ollama` after `ollama pull qwen3:1.7b`
(`SETUP.md`'s default model, mirrors `test_chat_ollama.py`).

Drives the compiled agent graph end-to-end through
`turn_service.run_chat_turn`, and asserts that every `[G...]`/`[S...]` marker
a real model puts in its reply is one of the opaque ids that turn's own tool
results actually carried — never a small sequential guess like `[G1]`/`[S1]`
would have satisfied under the pre-ADR-022, position-reconstructed scheme.
Graph/vector stores are real (`KuzuGraphStore`/`ChromaVectorStore` against
`tmp_path`) with a fake embedder, mirroring `agent_tools/conftest.py`'s unit
tests — only the chat model is real, so retrieval scoring stays
deterministic while tool selection and reply composition are genuine model
output."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from mythrix.agent.citations import extract_markers
from mythrix.agent.context import AgentContext
from mythrix.agent.graph import compile_agent_graph
from mythrix.agent.sessions import SessionStore
from mythrix.agent.tools import build_tools
from mythrix.agent.turn_service import run_chat_turn
from mythrix.core.bootstrap import Stores
from mythrix.core.chat import OllamaChatClient
from mythrix.core.config import Settings
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.models import Citation, Interpretant, Manifestation, Sign, Source, Tradition
from mythrix.core.ollama import create_chat_model, derive_chat_model
from mythrix.core.vector.chunking import Chunk
from mythrix.core.vector.store import ChromaVectorStore, ChunkMetadata

GENERATION_MODEL = "qwen3:1.7b"
BASE_URL = "http://localhost:11434"
CREATED_AT = datetime(2026, 1, 1, tzinfo=UTC)

RIDER_WAITE = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")

_CITATION_FAILURE_SNIPPET = "couldn't actually back up"


class FakeEmbedder:
    """Every text embeds to the same vector, so retrieval scoring is
    deterministic (every candidate ties) while the chat model above it is
    real — the same trick `agent_tools/conftest.py`'s unit tests use, applied
    here against a real qwen3 model instead of a fake `ChatClient`."""

    model_name = "fake-embed"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def _seed_stores(tmp_path: Path) -> Stores:
    graph_store = KuzuGraphStore(tmp_path / "graph.kuzu")
    graph_store.upsert_tradition(RIDER_WAITE)

    waite_source = Source(id="waite", domain="tarot", title="The Pictorial Key to the Tarot", author="A. E. Waite")
    graph_store.upsert_source(waite_source)
    # A source deliberately unrelated to tarot (see `feedback_symbol_study_corpus_design`
    # memory) — the point of these assertions is that a real model's citation
    # markers trace back to actual tool-supplied ids, not that the corpus
    # content is topically related to the sign it's cited against.
    genesis_source = Source(id="genesis", domain="tarot", title="Genesis", author="")
    graph_store.upsert_source(genesis_source)

    the_sun = Sign(
        id="the-sun", slug="the-sun", canonical_name="The Sun", sign_type="major-arcana", semiotic_system="tarot"
    )
    sun_manifestation = Manifestation(
        id="the-sun::rider-waite",
        sign_id="the-sun",
        tradition=RIDER_WAITE,
        display_name="The Sun",
        denotation="Joy, vitality, and the clarity of illuminated truth.",
        interpretants=(Interpretant(id="interp-sun-joy", type="concept", value="joy"),),
        citations=(Citation(source=waite_source, locator="p. 143"),),
        created_at=CREATED_AT,
    )
    graph_store.upsert_sign_with_manifestation(the_sun, sun_manifestation)

    vector_store = ChromaVectorStore(tmp_path / "chroma")
    genesis_verses = [
        "And God saw the light, that it was good: and God divided the light from the darkness.",
        "And God said, Let there be lights in the firmament of the heaven to divide the day from the night.",
        "And Cain was very wroth, and his countenance fell.",
        "And Joseph's brethren envied him, but his father observed the saying.",
        "And there was great gladness in the land, and the people rejoiced before the Lord.",
    ]
    chunks = [
        Chunk(index=i, text=text, char_start=0, char_end=len(text), ordinal=i, section="Genesis")
        for i, text in enumerate(genesis_verses)
    ]
    vector_store.add_chunks(
        chunks,
        embeddings=[[1.0, 0.0]] * len(chunks),
        metadata=ChunkMetadata(
            source_id="genesis", domain="tarot", embedding_model="fake-embed", ingested_at="2026-01-01T00:00:00+00:00"
        ),
    )
    return Stores(graph_store=graph_store, vector_store=vector_store, embedder=FakeEmbedder())


@pytest.fixture(scope="module")
def stores(tmp_path_factory: pytest.TempPathFactory) -> Stores:
    return _seed_stores(tmp_path_factory.mktemp("grounding-ids"))


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings(
        retrieval_match_pool_size=30, retrieval_min_score=0.0, region_window_size=3, region_min_interpretants=1
    )


@pytest.fixture(scope="module")
def graph(stores: Stores, settings: Settings) -> CompiledStateGraph:
    """Built once per module: `create_chat_model` validates the daemon on
    construction, so sharing one compiled graph across this file's tests
    avoids re-validating it per test (mirrors `api/dependencies.py`'s
    once-per-process construction)."""
    llm = create_chat_model(model=GENERATION_MODEL, base_url=BASE_URL, num_ctx=8192)
    toolset = build_tools(stores, settings, OllamaChatClient(llm))
    agent_llm = derive_chat_model(llm, num_predict=2048)
    return compile_agent_graph(
        agent_llm.bind_tools(toolset.model_tools),
        toolset,
        augment_max_regions=settings.augment_max_regions,
        augment_consolidation_group_size=settings.augment_consolidation_group_size,
        citation_max_retries=settings.citation_max_retries,
    )


def _tool_messages(history: list, since: int) -> list[ToolMessage]:
    return [m for m in history[since:] if isinstance(m, ToolMessage)]


def _final_ai_message_text(history: list, since: int) -> str:
    """`TurnEvent.reply_text` (what `run_chat_turn` returns) has already had
    every valid `[G...]`/`[S...]` marker stripped out by
    `turn_service.py::run_chat_turn` — `strip_markers` runs unconditionally
    on a validated reply before it's handed back, since the marker's job is
    citation *validation*, not display. Marker presence has to be checked
    against the raw model output instead: the last `AIMessage` this turn
    added to `session.history`, which is never stripped — the same text
    `_ungrounded_markers` itself validates against."""
    ai_messages = [m for m in history[since:] if isinstance(m, AIMessage)]
    assert ai_messages, "the turn should have produced at least one AI message"
    return str(ai_messages[-1].content)


def _grounding_ids(tool_messages: list[ToolMessage]) -> set[str]:
    """The real opaque `grounding_id`s a turn's tool results carried —
    reconstructed independently here (not imported from
    `turn_service._build_valid_marker_ids`) so this test would fail if that
    function's reading of a tool payload's shape ever drifted from what the
    tools actually return."""
    ids: set[str] = set()
    for message in tool_messages:
        payload = json.loads(str(message.content))
        if message.name == "get_sign" and isinstance(payload, dict):
            ids.update(c["grounding_id"] for c in payload.get("citations", ()))
        elif message.name == "query_sign" and isinstance(payload, dict):
            for region in payload.get("regions", ()):
                ids.update(seg["grounding_id"] for seg in region.get("segments", ()))
        elif message.name == "fetch_segments" and isinstance(payload, list):
            ids.update(seg["grounding_id"] for seg in payload if "grounding_id" in seg)
    return ids


def _assert_reply_cites_real_ids(
    reply_text: str, raw_ai_text: str, tool_messages: list[ToolMessage], prefix: str
) -> None:
    """The shared assertion every case below makes: the delivered reply isn't
    the citation-failure fallback, the turn's tools actually returned at
    least one citable item, the model's raw output named at least one
    marker, and every marker it named is a real tool-supplied id — never a
    guess. Markers are checked against `raw_ai_text` (the unstripped
    `AIMessage`), not `reply_text` — see `_final_ai_message_text`."""
    assert _CITATION_FAILURE_SNIPPET not in reply_text
    valid_ids = _grounding_ids(tool_messages)
    assert valid_ids, f"the tool call should have returned at least one {prefix}-prefixed item"

    markers = set(extract_markers(raw_ai_text))
    assert markers, "the reply should cite the item(s) it drew on"
    assert markers <= valid_ids
    # "<prefix>" + uuid4().hex[:6] (ADR-022) — not the small sequential
    # "G1"/"S1" the pre-ADR-022, position-reconstructed scheme would have
    # produced. Every marker must have that shape, but a turn may legitimately
    # call more than one tool (e.g. get_sign for context alongside query_sign
    # for corpus evidence) — only at least one marker needs to carry this
    # test's own prefix.
    assert all(len(marker) == 7 for marker in markers)
    assert any(marker.startswith(prefix) for marker in markers)


@pytest.mark.requires_ollama
def test_list_semiotic_systems_answers_from_the_real_graph(graph: CompiledStateGraph) -> None:
    sessions = SessionStore()
    turn = run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id="list-systems",
        message="What semiotic systems are available?",
        ui_selection=AgentContext(),
        max_tool_iterations=8,
    )

    assert "tarot" in turn.reply_text.lower()


@pytest.mark.requires_ollama
def test_get_sign_reply_cites_the_real_opaque_grounding_id_when_asked_to_cite(graph: CompiledStateGraph) -> None:
    sessions = SessionStore()
    session_id = "get-sign-primed"
    turn = run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id=session_id,
        message="Tell me about the sun in the Rider-Waite tradition, and cite the source for its meaning.",
        ui_selection=AgentContext(semiotic_system="tarot", tradition="rider-waite"),
        max_tool_iterations=8,
    )

    history = sessions.get_or_create(session_id).history
    tool_messages = _tool_messages(history, since=0)
    raw_ai_text = _final_ai_message_text(history, since=0)
    _assert_reply_cites_real_ids(turn.reply_text, raw_ai_text, tool_messages, prefix="G")


@pytest.mark.requires_ollama
def test_get_sign_reply_cites_the_real_opaque_grounding_id_unprompted(graph: CompiledStateGraph) -> None:
    """No "cite"/"quote" instruction anywhere in the user's message — a marker
    should still appear because `SYSTEM_PROMPT`'s response rules mandate it
    unconditionally ("Copy that id verbatim whenever referencing, quoting, or
    analyzing the item"), not because this turn's own wording asked for one."""
    sessions = SessionStore()
    session_id = "get-sign-unprompted"
    turn = run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id=session_id,
        message="Tell me about the sun in the Rider-Waite tradition.",
        ui_selection=AgentContext(semiotic_system="tarot", tradition="rider-waite"),
        max_tool_iterations=8,
    )

    history = sessions.get_or_create(session_id).history
    tool_messages = _tool_messages(history, since=0)
    raw_ai_text = _final_ai_message_text(history, since=0)
    _assert_reply_cites_real_ids(turn.reply_text, raw_ai_text, tool_messages, prefix="G")


@pytest.mark.requires_ollama
def test_query_sign_reply_cites_real_opaque_segment_ids_when_asked_to_cite(graph: CompiledStateGraph) -> None:
    sessions = SessionStore()
    session_id = "query-sign-primed"
    turn = run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id=session_id,
        message=(
            "What evidence supports the sun in the corpus? "
            "Quote the passages and describe the emotions expressed in them."
        ),
        ui_selection=AgentContext(semiotic_system="tarot", tradition="rider-waite"),
        max_tool_iterations=8,
    )

    history = sessions.get_or_create(session_id).history
    tool_messages = _tool_messages(history, since=0)
    raw_ai_text = _final_ai_message_text(history, since=0)
    _assert_reply_cites_real_ids(turn.reply_text, raw_ai_text, tool_messages, prefix="S")


@pytest.mark.requires_ollama
def test_query_sign_reply_cites_real_opaque_segment_ids_unprompted(graph: CompiledStateGraph) -> None:
    """No "quote"/"cite" instruction — only enough wording to select the
    right tool (`query_sign`'s own docstring trigger phrase, "what evidence
    supports X"). Any marker in the reply must still be real, and the system
    prompt's mandate must be what puts it there."""
    sessions = SessionStore()
    session_id = "query-sign-unprompted"
    turn = run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id=session_id,
        message="What evidence supports the sun?",
        ui_selection=AgentContext(semiotic_system="tarot", tradition="rider-waite"),
        max_tool_iterations=8,
    )

    history = sessions.get_or_create(session_id).history
    tool_messages = _tool_messages(history, since=0)
    raw_ai_text = _final_ai_message_text(history, since=0)
    _assert_reply_cites_real_ids(turn.reply_text, raw_ai_text, tool_messages, prefix="S")
