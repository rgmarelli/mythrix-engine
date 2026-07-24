"""Shared embedding abstraction — used by both the document loader (embedding
chunks at ingestion time) and the retrieval pipeline (embedding query text at
query time), so both go through the identical interface and a test can inject
one fake instead of requiring a running Ollama daemon (plan.md Risks: "Testing
LLM-dependent code")."""

from __future__ import annotations

from typing import Protocol

from mythrix.core.errors import ModelRequestError, ModelUnavailableError


class Embedder(Protocol):
    model_name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbedder:
    """Real `OllamaEmbeddings`-backed `Embedder`. Exercised directly only by
    `@pytest.mark.requires_ollama` integration tests — unit tests inject a fake
    `Embedder` instead."""

    def __init__(self, *, model: str, base_url: str) -> None:
        from langchain_ollama import OllamaEmbeddings

        self.model_name = model
        self._embeddings = OllamaEmbeddings(model=model, base_url=base_url)

    def embed(self, texts: list[str]) -> list[list[float]]:
        from ollama import ResponseError

        try:
            return self._embeddings.embed_documents(texts)
        except ResponseError as exc:
            if exc.status_code == 404:
                raise ModelUnavailableError(self.model_name) from exc
            raise ModelRequestError(self.model_name, cause=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - connection drops, timeouts, etc: surface the real cause
            raise ModelRequestError(self.model_name, cause=f"{type(exc).__name__}: {exc}") from exc
