"""Unit tests for `OllamaChatClient` (T37, reduced from T18/T30's `OllamaSynthesizer`):
actionable-error paths only. No running Ollama is used or required — the
unset-model check short-circuits before any client is built, and the
unreachable-base-url case exercises exactly the "Ollama unavailable" failure
path, fast and offline.

The orchestration this module used to test (`synthesize()`, concept/general
prompt assembly, two-level citation validation) is retired — the `query`
path invokes no generation model at all (FR-RT-10). What remains is a minimal
chat client retained for a future conversational agent loop; see
`synthesis/chain.py`'s module docstring.
"""

import pytest

from mythrix.core.errors import ModelUnavailableError
from mythrix.core.synthesis.chain import ChatClient, OllamaChatClient


def test_unset_generation_model_raises_actionable_error_immediately() -> None:
    with pytest.raises(ModelUnavailableError):
        OllamaChatClient(generation_model="", base_url="http://localhost:11434")


def test_unreachable_ollama_raises_model_unavailable_error() -> None:
    with pytest.raises(ModelUnavailableError):
        OllamaChatClient(generation_model="llama3", base_url="http://localhost:1")


class FakeChatClient:
    """A `ChatClient` a future agent loop could inject in place of
    `OllamaChatClient` — just enough surface for that Protocol."""

    generation_model = "fake-model"

    def __init__(self, response: str) -> None:
        self._response = response

    def invoke(self, prompt: str) -> str:
        return self._response


def test_fake_chat_client_satisfies_the_protocol() -> None:
    client: ChatClient = FakeChatClient("Fire [G1] [S1] dominates this concept.")

    assert client.invoke("any prompt") == "Fire [G1] [S1] dominates this concept."
    assert client.generation_model == "fake-model"
