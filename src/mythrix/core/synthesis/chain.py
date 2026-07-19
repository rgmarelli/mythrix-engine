"""LangChain + Ollama synthesis (FR9, FR11, FR12) behind a `Synthesizer`
Protocol, so tests inject a fake instead of requiring a running Ollama daemon
(plan.md Risks: "Testing LLM-dependent code"). The LLM never gets tool-calling
access to the graph or vector store (FR10) — `OllamaSynthesizer` only ever
sends it the rendered `build_prompt(context)` text and reads back a narrative,
which `validate_citations` then checks in code (FR12).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from mythrix.core.errors import ModelRequestError, ModelUnavailableError
from mythrix.core.models import InterpretationResult, RetrievalContext
from mythrix.core.synthesis.citations import validate_citations
from mythrix.core.synthesis.prompts import build_prompt


class Synthesizer(Protocol):
    generation_model: str

    def synthesize(self, context: RetrievalContext) -> InterpretationResult: ...


class OllamaSynthesizer:
    """Real `ChatOllama`-backed `Synthesizer`. Exercised directly only by the
    opt-in `@pytest.mark.requires_ollama` test in `tests/integration/` — unit
    tests cover the wiring (prompt assembly, citation validation, result shape)
    against a fake `Synthesizer` instead."""

    def __init__(
        self, *, generation_model: str, embedding_model: str, base_url: str, temperature: float = 0.15
    ) -> None:
        if not generation_model:
            raise ModelUnavailableError(generation_model or "<unset>")

        self.generation_model = generation_model
        self._embedding_model = embedding_model
        try:
            from langchain_ollama import ChatOllama

            self._llm = ChatOllama(
                model=generation_model, base_url=base_url, temperature=temperature, validate_model_on_init=True
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

    def synthesize(self, context: RetrievalContext) -> InterpretationResult:
        from ollama import ResponseError

        prompt = build_prompt(context)
        try:
            response = self._llm.invoke(prompt)
        except ResponseError as exc:
            if exc.status_code == 404:
                raise ModelUnavailableError(self.generation_model) from exc
            raise ModelRequestError(self.generation_model, cause=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - connection drops, timeouts, etc: surface the real cause
            raise ModelRequestError(self.generation_model, cause=f"{type(exc).__name__}: {exc}") from exc

        narrative = str(response.content)
        invalid_markers = validate_citations(narrative, context)
        return InterpretationResult(
            context=context,
            narrative=narrative,
            generation_model=self.generation_model,
            embedding_model=self._embedding_model,
            citation_markers_valid=not invalid_markers,
            invalid_markers=invalid_markers,
            generated_at=datetime.now(UTC),
        )
