"""`FastAPI()` factory: builds `Stores` once at process startup (`lifespan`),
registers the `/api` router before the conditional `web/dist` static mount
(mount order matters — a `Mount("/")` registered first shadows `/api/*`),
and enables CORS for the Vite dev server."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from mythrix.agent.sessions import SessionStore
from mythrix.api import routes
from mythrix.api.errors import register_exception_handlers
from mythrix.core.bootstrap import build_stores
from mythrix.core.config import Settings
from mythrix.core.logging_config import configure_logging

_REPO_ROOT = Path(__file__).resolve().parents[4]
_WEB_DIST = _REPO_ROOT / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.stores = build_stores(Settings())
    app.state.agent_sessions = SessionStore()
    # Not built eagerly, unlike `stores`: it needs a live, configured Ollama
    # daemon, which is not the common deployment case (`get_chat_client`'s
    # docstring) — `get_agent_graph` builds it lazily on first chat turn.
    app.state.agent_graph = None
    yield


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Mythrix Query Viewer API", lifespan=lifespan)

    web_origin = os.environ.get("MYTHRIX_WEB_ORIGIN", "http://localhost:5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[web_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(routes.router, prefix="/api")

    if _WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="web")

    return app


app = create_app()
