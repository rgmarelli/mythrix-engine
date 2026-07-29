# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for core.errors: all errors subclass MythrixError and carry a useful message."""

import pytest

from mythrix.core.errors import (
    CitationValidationError,
    EmbeddingModelMismatchError,
    IngestValidationError,
    ModelUnavailableError,
    MythrixError,
    SignNotFoundError,
    TraditionNotFoundError,
)


@pytest.mark.parametrize(
    ("error", "expected_fragments"),
    [
        (SignNotFoundError("the-tower"), ["the-tower"]),
        (TraditionNotFoundError("rider-waite"), ["rider-waite"]),
        (
            IngestValidationError("dangling citation", source_path="signs/the-tower.yaml"),
            ["dangling citation", "signs/the-tower.yaml"],
        ),
        (CitationValidationError(("[S9]", "[G4]")), ["[S9]", "[G4]"]),
        (ModelUnavailableError("llama3.1"), ["llama3.1", "ollama pull"]),
        (
            EmbeddingModelMismatchError("nomic-embed-text", "mxbai-embed-large"),
            ["nomic-embed-text", "mxbai-embed-large"],
        ),
    ],
)
def test_error_is_mythrix_error_with_useful_message(error: MythrixError, expected_fragments: list[str]) -> None:
    assert isinstance(error, MythrixError)
    message = str(error)
    assert message
    for fragment in expected_fragments:
        assert fragment in message
