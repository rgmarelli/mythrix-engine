# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Real-Ollama coverage for the consolidated construction path — opt-in, since
it needs a running local Ollama daemon with the model pulled. Not run as part
of the default `pytest tests/unit` suite; run explicitly with
`pytest tests/integration -m requires_ollama` after `ollama pull llama3.2`.

The query path itself invokes no generation model (FR-RT-10) — this exists to
confirm `create_chat_model` and the `OllamaChatClient` adapter over it still
work against a real daemon, which no unit test can establish.
"""

import pytest

from mythrix.core.chat import OllamaChatClient
from mythrix.core.ollama import create_chat_model

GENERATION_MODEL = "llama3.2"
BASE_URL = "http://localhost:11434"


@pytest.mark.requires_ollama
def test_real_chat_client_returns_a_response() -> None:
    client = OllamaChatClient(create_chat_model(model=GENERATION_MODEL, base_url=BASE_URL))

    response = client.invoke("Reply with exactly the word: OK")

    assert response.strip() != ""


@pytest.mark.requires_ollama
def test_both_agent_roles_derive_from_one_validated_model() -> None:
    """FR-03/FR-04: `bind_tools` binds over the same instance the summarize
    client wraps, so the daemon is validated once."""
    llm = create_chat_model(model=GENERATION_MODEL, base_url=BASE_URL)

    bound = llm.bind_tools([], num_predict=2048)

    assert OllamaChatClient(llm).generation_model == GENERATION_MODEL
    assert bound.bound is llm
