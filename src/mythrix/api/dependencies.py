"""`Stores` is built once at process startup (`app.py`'s `lifespan`) and
read from `app.state` per request — never rebuilt per request."""

from __future__ import annotations

from fastapi import Request

from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings
from mythrix.core.synthesis.chain import ChatClient, OllamaChatClient


def get_stores(request: Request) -> Stores:
    return request.app.state.stores


def get_chat_client() -> ChatClient:
    """Built fresh per request, unlike `Stores` — `generation_model` has no
    default (`core/config.py`) and most v1 deployments never set one;
    building it once at process startup would fail API startup for every
    deployment that never uses the AI Summary action."""
    settings = Settings()
    return OllamaChatClient(
        generation_model=settings.generation_model or "",
        base_url=settings.ollama_base_url,
        num_ctx=settings.generation_num_ctx,
    )
