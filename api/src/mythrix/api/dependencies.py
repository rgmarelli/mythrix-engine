"""`Stores` is built once at process startup (`app.py`'s `lifespan`) and
read from `app.state` per request — never rebuilt per request."""

from __future__ import annotations

from fastapi import Request
from langgraph.graph.state import CompiledStateGraph

from mythrix.agent.graph import build_agent_graph
from mythrix.agent.sessions import SessionStore
from mythrix.agent.tools import build_tools
from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings
from mythrix.core.synthesis.chain import OllamaChatClient


def get_stores(request: Request) -> Stores:
    return request.app.state.stores


def get_agent_sessions(request: Request) -> SessionStore:
    return request.app.state.agent_sessions


def get_agent_graph(request: Request) -> CompiledStateGraph:
    """Lazy-build-once-then-cache, unlike `get_stores` (built eagerly at
    `lifespan`): building the tool-calling graph unconditionally at
    `lifespan` would fail API startup for any deployment with no agent/
    generation model configured — `generation_model` has no default
    (`core/config.py`) and most v1 deployments never set one. A build
    failure raises a `MythrixError` subclass for an unreachable/unconfigured
    model, handled by the registered exception handler (502) — just
    surfacing on the first chat turn instead of at server startup."""
    if request.app.state.agent_graph is None:
        settings = Settings()
        stores = request.app.state.stores
        generation_model = settings.agent_model or settings.generation_model or ""
        chat_client = OllamaChatClient(
            generation_model=generation_model,
            base_url=settings.ollama_base_url,
            num_ctx=settings.generation_num_ctx,
        )
        tools = build_tools(stores, settings, chat_client)
        request.app.state.agent_graph = build_agent_graph(
            generation_model=generation_model,
            base_url=settings.ollama_base_url,
            num_ctx=settings.generation_num_ctx,
            tools=tools,
        )
    return request.app.state.agent_graph
