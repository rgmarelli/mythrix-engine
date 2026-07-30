# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""`MythrixError`-family to HTTP status mapping (`specs/interfaces/api.md`).
Covers every route directly, including
`/api/query`, which returns its whole response in one JSON payload — no
separate mid-request error path to handle."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mythrix.core.errors import (
    AdhocQueryValidationError,
    EmbeddingModelMismatchError,
    IngestValidationError,
    ManifestationNotFoundError,
    ModelRequestError,
    ModelUnavailableError,
    MythrixError,
    RegionNotFoundError,
    SignNotFoundError,
    SourceNotFoundError,
    TraditionNotFoundError,
)

_NOT_FOUND = (
    SignNotFoundError,
    TraditionNotFoundError,
    ManifestationNotFoundError,
    SourceNotFoundError,
    RegionNotFoundError,
)
_MODEL_UNREACHABLE = (ModelUnavailableError, ModelRequestError, EmbeddingModelMismatchError)
_VALIDATION_ERROR = (IngestValidationError, AdhocQueryValidationError)


def status_code_for(exc: MythrixError) -> int:
    if isinstance(exc, _NOT_FOUND):
        return 404
    if isinstance(exc, _MODEL_UNREACHABLE):
        return 502
    if isinstance(exc, _VALIDATION_ERROR):
        return 422
    return 500


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(MythrixError)
    async def _handle_mythrix_error(request: Request, exc: MythrixError) -> JSONResponse:  # noqa: ARG001
        return JSONResponse(status_code=status_code_for(exc), content={"detail": str(exc)})
