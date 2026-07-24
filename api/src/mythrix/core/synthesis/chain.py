"""Ollama chat client (FR-RT-02) retained for a future conversational agent loop
(spec.md's non-goal on conversational request parsing) — the `query` path
itself invokes no generation model at all (FR-RT-10). `OllamaChatClient` only
ever sends rendered prompt text and reads back plain text; it has no
tool-calling access to the graph or vector store, by construction. Whatever
context an agent loop assembles for it should use `synthesis/prompts.py`'s
`[G#]`/`[S#]` rendering, so `synthesis/citations.py` can validate the result
the same way this project always has.

Retained from the pre-Phase-11 synthesis orchestration: the `ChatOllama`
construction and its error mapping. The mapping matches on *message text*
because `validate_model_on_init` raises inconsistent exception types across
`langchain_ollama`/`httpx` versions for "model not pulled" and "daemon
unreachable" alike — established empirically (plan.md's "LangChain + Ollama
synthesis"), not something to rediscover later. Removed: the per-concept and
general-summary orchestration (`synthesize()`/`_synthesize_concept()`) — the
query path no longer produces synthesized text at all (FR-RT-10).
"""

from __future__ import annotations

from typing import Protocol

from mythrix.core.errors import ModelRequestError, ModelUnavailableError


class ChatClient(Protocol):
    generation_model: str

    def invoke(self, prompt: str) -> str: ...


class OllamaChatClient:
    """Real `ChatOllama`-backed `ChatClient`. Exercised directly only by the
    opt-in `@pytest.mark.requires_ollama` test in `tests/integration/`; unit
    tests inject a fake instead."""

    def __init__(
        self,
        *,
        generation_model: str,
        base_url: str,
        temperature: float = 0.15,
        num_ctx: int = 8192,
    ) -> None:
        if not generation_model:
            raise ModelUnavailableError(generation_model or "<unset>")

        self.generation_model = generation_model
        try:
            from langchain_ollama import ChatOllama

            self._llm = ChatOllama(
                model=generation_model,
                base_url=base_url,
                temperature=temperature,
                num_ctx=num_ctx,
                validate_model_on_init=True,
            )
        except Exception as exc:  # noqa: BLE001 - validate_model_on_init raises inconsistent exception
            # types across langchain_ollama/httpx versions for "model not found" and
            # "can't reach the daemon at all" alike, so match on message rather than
            # type — both are in the same actionable "pull the model / start Ollama"
            # family. Anything else is a genuinely unexpected failure; surface it.
            message = str(exc)
            if "not found in Ollama" in message or "Failed to connect to Ollama" in message:
                raise ModelUnavailableError(generation_model) from exc
            raise ModelRequestError(generation_model, cause=f"{type(exc).__name__}: {message}") from exc

    def invoke(self, prompt: str) -> str:
        from ollama import ResponseError

        try:
            response = self._llm.invoke(prompt)
        except ResponseError as exc:
            if exc.status_code == 404:
                raise ModelUnavailableError(self.generation_model) from exc
            raise ModelRequestError(self.generation_model, cause=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - connection drops, timeouts, etc: surface the real cause
            raise ModelRequestError(self.generation_model, cause=f"{type(exc).__name__}: {exc}") from exc
        return str(response.content)
