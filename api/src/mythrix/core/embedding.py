# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared embedding abstraction — used by both the document loader (embedding
chunks at ingestion time) and the retrieval pipeline (embedding query text at
query time), so both go through the identical interface and a test can inject
one fake instead of requiring a running Ollama daemon."""

from __future__ import annotations

from typing import Protocol

from mythrix.core.ollama import create_embeddings, model_errors


class Embedder(Protocol):
    model_name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbedder:
    """Real `OllamaEmbeddings`-backed `Embedder`. Exercised directly only by
    `@pytest.mark.requires_ollama` integration tests — unit tests inject a fake
    `Embedder` instead."""

    def __init__(self, *, model: str, base_url: str) -> None:
        self.model_name = model
        self._embeddings = create_embeddings(model=model, base_url=base_url)

    def embed(self, texts: list[str]) -> list[list[float]]:
        with model_errors(self.model_name):
            return self._embeddings.embed_documents(texts)
