# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The single point of contact with the local Ollama daemon: the only module
that imports `langchain_ollama` or `ollama`, and the only definition of how a
daemon failure becomes a `MythrixError`.

It owns *infrastructure* — how to build a client, how to translate a failure.
It does not decide what a caller may do with one: that is the job of the role
adapters (`core/chat.py`'s `ChatClient`, `core/embedding.py`'s `Embedder`),
whose narrowness is the ADR-006 orchestration boundary. Construction being
shared does not widen either adapter.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from mythrix.core.errors import ModelRequestError, ModelUnavailableError

if TYPE_CHECKING:
    from langchain_ollama import ChatOllama, OllamaEmbeddings


def create_chat_model(
    *,
    model: str,
    base_url: str,
    temperature: float = 0.15,
    num_ctx: int = 8192,
) -> ChatOllama:
    """A `ChatOllama` validated against the daemon at construction, so an
    unreachable daemon or an uninstalled model fails here rather than mid-turn
    (agent.md FR-AG-08).

    `validate_model_on_init` raises inconsistent exception *types* across
    `langchain_ollama`/`httpx` versions for "model not found" and "can't reach
    the daemon at all" alike, so the mapping matches on message text rather
    than type — both belong to the same actionable "pull the model / start
    Ollama" family. Anything else is a genuinely unexpected failure and is
    surfaced as `ModelRequestError` with its real cause attached.
    """
    if not model:
        raise ModelUnavailableError(model or "<unset>")

    from langchain_ollama import ChatOllama

    try:
        return ChatOllama(
            model=model,
            base_url=base_url,
            temperature=temperature,
            num_ctx=num_ctx,
            validate_model_on_init=True,
        )
    except Exception as exc:  # noqa: BLE001 - see docstring on why this is matched by message, not type
        message = str(exc)
        if "not found in Ollama" in message or "Failed to connect to Ollama" in message:
            raise ModelUnavailableError(model) from exc
        raise ModelRequestError(model, cause=f"{type(exc).__name__}: {message}") from exc


def derive_chat_model(llm: ChatOllama, **generation_options: object) -> ChatOllama:
    """A variant of an already-validated chat model carrying different
    generation parameters, for a caller whose role needs them (e.g. the agent's
    larger output budget) — without a second construction or a second daemon
    round-trip. The copy shares the original's HTTP client.

    Deriving, rather than binding: `ChatOllama` folds its *constructor* fields
    into the `options` of each request, but an `options` value supplied at bind
    time replaces that dict wholesale rather than merging into it, and any other
    bound keyword is sent as a top-level request argument the Ollama client
    rejects. Setting the field on a copy is what puts a per-role parameter in
    `options` alongside the construction-time ones.
    """
    return llm.model_copy(update=generation_options)


def create_embeddings(*, model: str, base_url: str) -> OllamaEmbeddings:
    """An `OllamaEmbeddings` client. Unlike `create_chat_model` there is no
    construction-time validation to do — `OllamaEmbeddings` contacts the daemon
    only on the first `embed_documents` call, so an unavailable model surfaces
    through `model_errors` instead."""
    from langchain_ollama import OllamaEmbeddings

    return OllamaEmbeddings(model=model, base_url=base_url)


@contextmanager
def model_errors(model_name: str) -> Iterator[None]:
    """Maps a call-time Ollama failure onto the actionable error pair: a 404
    `ResponseError` means the model is not installed
    (`ModelUnavailableError`); anything else — another `ResponseError`, a
    dropped connection, a timeout — is a `ModelRequestError` carrying its real
    cause."""
    from ollama import ResponseError

    try:
        yield
    except ResponseError as exc:
        if exc.status_code == 404:
            raise ModelUnavailableError(model_name) from exc
        raise ModelRequestError(model_name, cause=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - connection drops, timeouts, etc: surface the real cause
        raise ModelRequestError(model_name, cause=f"{type(exc).__name__}: {exc}") from exc
