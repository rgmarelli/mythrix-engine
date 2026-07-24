"""Real-Ollama coverage for `OllamaChatClient` (T18, reduced by T37) — opt-in,
since it needs a running local Ollama daemon with the model pulled. Not run
as part of the default `pytest tests/unit` suite; run explicitly with
`pytest tests/integration -m requires_ollama` after `ollama pull llama3.2`
(or point `--generation-model` at whatever's installed locally).

The `query` path itself invokes no generation model (FR-RT-10) — this test
exists only to confirm `OllamaChatClient` still works against a real daemon,
for the planned conversational agent loop that will use it.
"""

import pytest

from mythrix.core.synthesis.chain import OllamaChatClient

GENERATION_MODEL = "llama3.2"


@pytest.mark.requires_ollama
def test_real_chat_client_returns_a_response() -> None:
    client = OllamaChatClient(generation_model=GENERATION_MODEL, base_url="http://localhost:11434")

    response = client.invoke("Reply with exactly the word: OK")

    assert response.strip() != ""
