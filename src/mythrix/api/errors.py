"""`MythrixError`-family to HTTP status mapping (FR9, FR10 of
`specs/query-viewer-web-ui/spec.md`). Covers every route directly, including
`/api/query`, which returns its whole response in one JSON payload — no
separate mid-request error path to handle."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mythrix.core.errors import (
    EmbeddingModelMismatchError,
    IngestValidationError,
    ManifestationNotFoundError,
    ModelRequestError,
    ModelUnavailableError,
    MythrixError,
    SignNotFoundError,
    SourceNotFoundError,
    TraditionNotFoundError,
)

_NOT_FOUND = (SignNotFoundError, TraditionNotFoundError, ManifestationNotFoundError, SourceNotFoundError)
_MODEL_UNREACHABLE = (ModelUnavailableError, ModelRequestError, EmbeddingModelMismatchError)
_VALIDATION_ERROR = (IngestValidationError,)


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
