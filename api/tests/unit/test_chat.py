# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `core/chat.py::OllamaChatClient` — the adapter's surface and
its error mapping over an injected chat model. Construction and daemon
validation live in `core/ollama.py` and are tested in `test_ollama.py`; no
running Ollama is used or required here."""

import pytest

from mythrix.core.chat import ChatClient, OllamaChatClient
from mythrix.core.errors import ModelRequestError, ModelUnavailableError


class FakeLlm:
    """The `ChatOllama` surface `OllamaChatClient` actually depends on: a
    `model` attribute and `invoke`."""

    def __init__(self, response: object = None, raises: Exception | None = None) -> None:
        self.model = "fake-model"
        self._response = response
        self._raises = raises

    def invoke(self, prompt: str):  # noqa: ANN201 - mimics ChatOllama's AIMessage return
        if self._raises is not None:
            raise self._raises
        return self._response


class _Reply:
    def __init__(self, content: str) -> None:
        self.content = content


def test_client_reads_its_model_name_from_the_injected_model() -> None:
    """`ChatClient.generation_model` is derived, not passed separately — it
    cannot disagree with the model actually being called."""
    assert OllamaChatClient(FakeLlm()).generation_model == "fake-model"


def test_invoke_returns_the_response_content_as_text() -> None:
    client = OllamaChatClient(FakeLlm(response=_Reply("Fire dominates this concept.")))

    assert client.invoke("any prompt") == "Fire dominates this concept."


def test_a_missing_model_at_call_time_raises_model_unavailable_error() -> None:
    from ollama import ResponseError

    client = OllamaChatClient(FakeLlm(raises=ResponseError("model not found", status_code=404)))

    with pytest.raises(ModelUnavailableError):
        client.invoke("any prompt")


def test_any_other_failure_raises_model_request_error() -> None:
    client = OllamaChatClient(FakeLlm(raises=TimeoutError("read timed out")))

    with pytest.raises(ModelRequestError):
        client.invoke("any prompt")


def test_the_client_exposes_no_tool_binding_surface() -> None:
    """The ADR-006 boundary is structural: the summarize client cannot reach
    the corpus through a tool call because it has no way to bind one."""
    assert not hasattr(OllamaChatClient(FakeLlm()), "bind_tools")


class FakeChatClient:
    """A `ChatClient` a test can inject in place of `OllamaChatClient` — just
    enough surface for that Protocol."""

    generation_model = "fake-model"

    def __init__(self, response: str) -> None:
        self._response = response

    def invoke(self, prompt: str) -> str:
        return self._response


def test_fake_chat_client_satisfies_the_protocol() -> None:
    client: ChatClient = FakeChatClient("Fire [G1] [S1] dominates this concept.")

    assert client.invoke("any prompt") == "Fire [G1] [S1] dominates this concept."
    assert client.generation_model == "fake-model"
