"""`MythrixError`-family to HTTP status mapping (FR9, FR10 of
`specs/query-viewer-web-ui/spec.md`). Covers every route directly, and
`/api/query`'s pre-stream failures (see `routes.py`'s docstring on why a
mid-stream failure surfaces as an `error` SSE event instead)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mythrix.core.errors import (
    EmbeddingModelMismatchError,
    InterpretationNotFoundError,
    ModelRequestError,
    ModelUnavailableError,
    MythrixError,
    SymbolNotFoundError,
    TraditionNotFoundError,
)

_NOT_FOUND = (SymbolNotFoundError, TraditionNotFoundError, InterpretationNotFoundError)
_MODEL_UNREACHABLE = (ModelUnavailableError, ModelRequestError, EmbeddingModelMismatchError)


def status_code_for(exc: MythrixError) -> int:
    if isinstance(exc, _NOT_FOUND):
        return 404
    if isinstance(exc, _MODEL_UNREACHABLE):
        return 502
    return 500


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(MythrixError)
    async def _handle_mythrix_error(request: Request, exc: MythrixError) -> JSONResponse:  # noqa: ARG001
        return JSONResponse(status_code=status_code_for(exc), content={"detail": str(exc)})
