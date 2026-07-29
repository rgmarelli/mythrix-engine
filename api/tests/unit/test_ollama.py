# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for `core/ollama.py` — the one construction point and the one
failure mapping every Ollama-backed client in the system shares (FR-01, FR-02).

No running Ollama is used or required: the unset-model check short-circuits
before any client is built, the unreachable-base-url case exercises exactly
the "Ollama unavailable" path offline, and `model_errors` is a context manager
that can be driven with raised exceptions directly.
"""

import pytest

from mythrix.core.errors import ModelRequestError, ModelUnavailableError
from mythrix.core.ollama import model_errors


def test_unset_model_raises_actionable_error_before_touching_the_daemon() -> None:
    from mythrix.core.ollama import create_chat_model

    with pytest.raises(ModelUnavailableError):
        create_chat_model(model="", base_url="http://localhost:11434")


def test_unreachable_daemon_raises_model_unavailable_error() -> None:
    from mythrix.core.ollama import create_chat_model

    with pytest.raises(ModelUnavailableError):
        create_chat_model(model="llama3", base_url="http://localhost:1")


def test_derive_chat_model_carries_a_per_role_option_alongside_the_constructed_ones() -> None:
    """The regression this exists for: `ChatOllama` sends its *constructor*
    fields inside each request's `options`, but a keyword bound onto the model
    is sent as a top-level request argument, which the Ollama client rejects
    with `TypeError: Client.chat() got an unexpected keyword argument`. Setting
    the field on a copy is what puts it in `options` — alongside `num_ctx` and
    `temperature`, not replacing them.

    Builds `ChatOllama` directly rather than through `create_chat_model`: this
    asserts on request assembly, which needs no reachable daemon, so
    `validate_model_on_init` is deliberately left off.
    """
    from langchain_core.messages import HumanMessage
    from langchain_ollama import ChatOllama

    from mythrix.core.ollama import derive_chat_model

    base = ChatOllama(model="some-model", base_url="http://localhost:11434", temperature=0.15, num_ctx=8192)
    derived = derive_chat_model(base, num_predict=2048)

    base_options = base._chat_params([HumanMessage(content="x")])["options"]
    derived_options = derived._chat_params([HumanMessage(content="x")])["options"]

    assert derived_options == {**base_options, "num_predict": 2048}
    assert "num_predict" not in base_options


def test_derive_chat_model_reuses_the_originals_client() -> None:
    """FR-03: deriving must not cost a second daemon validation."""
    from langchain_ollama import ChatOllama

    from mythrix.core.ollama import derive_chat_model

    base = ChatOllama(model="some-model", base_url="http://localhost:11434")

    assert derive_chat_model(base, num_predict=2048)._client is base._client


def test_model_errors_maps_a_404_response_to_model_unavailable() -> None:
    from ollama import ResponseError

    with pytest.raises(ModelUnavailableError), model_errors("some-model"):
        raise ResponseError("model not found", status_code=404)


def test_model_errors_maps_a_non_404_response_to_model_request_error() -> None:
    from ollama import ResponseError

    with pytest.raises(ModelRequestError), model_errors("some-model"):
        raise ResponseError("server exploded", status_code=500)


def test_model_errors_maps_an_arbitrary_failure_to_model_request_error() -> None:
    """A dropped connection or timeout is not a "pull the model" problem — it
    surfaces with its real cause attached rather than as unavailability."""
    with pytest.raises(ModelRequestError) as exc_info, model_errors("some-model"):
        raise TimeoutError("read timed out")

    assert "TimeoutError" in str(exc_info.value)


def test_model_errors_is_transparent_when_nothing_fails() -> None:
    with model_errors("some-model"):
        result = "ok"

    assert result == "ok"
