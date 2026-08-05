# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared fixtures for `agent/tools/` unit tests — real
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
from mythrix.core.vector.store import ChromaVectorStore

RIDER_WAITE = Tradition(id="rider-waite", slug="rider-waite", name="Rider-Waite-Smith", domain="tarot")
MARSEILLE = Tradition(id="marseille", slug="marseille", name="Marseille", domain="tarot")
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

    the_sun = Sign(
        id="the-sun", slug="the-sun", canonical_name="The Sun", sign_type="major-arcana", semiotic_system="tarot"
    )
    sun_manifestation = Manifestation(
        id="the-sun::rider-waite",
        sign_id="the-sun",
        tradition=RIDER_WAITE,
        display_name="The Sun",
        created_at=CREATED_AT,
    )
    store.upsert_sign_with_manifestation(the_sun, sun_manifestation)

    he = Sign(id="he", slug="he", canonical_name="He", sign_type="hebrew-letter", semiotic_system="hebrew_alef_bet")
    he_manifestation = Manifestation(
        id="he::golden-dawn-kabbalah",
        sign_id="he",
        tradition=GOLDEN_DAWN,
        display_name="He",
        created_at=CREATED_AT,
    )
    store.upsert_sign_with_manifestation(he, he_manifestation)

    # A same-named pair, isolated to the semiotic-system-scoping tests below —
    # deliberately not reusing an existing sign's name so unrelated tests that
    # resolve "The Tower"/"The Magician"/etc. by name are unaffected.
    tarot_threshold = Sign(
        id="threshold-tarot",
        slug="threshold-tarot",
        canonical_name="Threshold",
        sign_type="major-arcana",
        semiotic_system="tarot",
    )
    tarot_threshold_manifestation = Manifestation(
        id="threshold-tarot::rider-waite",
        sign_id="threshold-tarot",
        tradition=RIDER_WAITE,
        display_name="Threshold",
        created_at=CREATED_AT,
    )
    store.upsert_sign_with_manifestation(tarot_threshold, tarot_threshold_manifestation)

    hebrew_threshold = Sign(
        id="threshold-hebrew",
        slug="threshold-hebrew",
        canonical_name="Threshold",
        sign_type="hebrew-letter",
        semiotic_system="hebrew_alef_bet",
    )
    hebrew_threshold_manifestation = Manifestation(
        id="threshold-hebrew::golden-dawn-kabbalah",
        sign_id="threshold-hebrew",
        tradition=GOLDEN_DAWN,
        display_name="Threshold",
        created_at=CREATED_AT,
    )
    store.upsert_sign_with_manifestation(hebrew_threshold, hebrew_threshold_manifestation)
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
        retrieval_match_pool_size=30,
        retrieval_min_score=0.0,
        region_window_size=3,
        region_min_interpretants=1,
    )


@pytest.fixture
def tools_by_name():
    def _build(stores: Stores, settings: Settings, chat_client) -> dict:  # noqa: ANN001
        return {t.name: t for t in build_tools(stores, settings, chat_client).all}

    return _build
