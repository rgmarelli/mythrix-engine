"""Ollama chat client (FR-RT-02) used by the conversational agent layer
(`mythrix.agent`) — the query path itself invokes no generation model at all
(FR-RT-10). `OllamaChatClient` only ever sends prompt text and reads back
plain text; it has no tool-binding surface, so it cannot reach the graph or
vector store through a tool call, by construction (ADR-006).

The agent's tool-bound model is a separate binding over the *same* underlying
chat model, derived alongside this adapter in `api/dependencies.py`. Sharing
the constructed model is what keeps the daemon validated once per process; it
does not widen this adapter, whose narrowness is the boundary itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from mythrix.core.ollama import model_errors

if TYPE_CHECKING:
    from mythrix.core.ollama import ChatOllama


class ChatClient(Protocol):
    generation_model: str

    def invoke(self, prompt: str) -> str: ...


class OllamaChatClient:
    """Text-in/text-out `ChatClient` over an already-constructed `ChatOllama`
    (`core/ollama.py::create_chat_model`). Exercised against a real daemon only
    by the opt-in `@pytest.mark.requires_ollama` test in `tests/integration/`;
    unit tests inject a fake `ChatClient` instead."""

    def __init__(self, llm: ChatOllama) -> None:
        self._llm = llm
        self.generation_model = llm.model

    def invoke(self, prompt: str) -> str:
        with model_errors(self.generation_model):
            response = self._llm.invoke(prompt)
        return str(response.content)
