# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared store construction for every process that runs a query: the CLI
(`cli/commands/query.py::query`) and the API (`api/app.py`'s `lifespan`)."""

from __future__ import annotations

from dataclasses import dataclass

from mythrix.core.config import Settings
from mythrix.core.embedding import Embedder, OllamaEmbedder
from mythrix.core.graph.store import KuzuGraphStore
from mythrix.core.vector.store import ChromaVectorStore


@dataclass(frozen=True)
class Stores:
    """The graph store, vector store, and embedder one process needs for the
    life of that process."""

    graph_store: KuzuGraphStore
    vector_store: ChromaVectorStore
    embedder: Embedder


def build_stores(settings: Settings) -> Stores:
    return Stores(
        graph_store=KuzuGraphStore(settings.kuzu_db_path),
        vector_store=ChromaVectorStore(settings.chroma_persist_dir),
        embedder=OllamaEmbedder(model=settings.embedding_model, base_url=settings.ollama_base_url),
    )
