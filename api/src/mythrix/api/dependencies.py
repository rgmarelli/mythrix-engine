# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""`Stores` is built once at process startup (`app.py`'s `lifespan`) and
read from `app.state` per request — never rebuilt per request."""

from __future__ import annotations

from fastapi import Request
from langgraph.graph.state import CompiledStateGraph

from mythrix.agent.graph import compile_agent_graph
from mythrix.agent.sessions import SessionStore
from mythrix.agent.tools import build_tools
from mythrix.core.bootstrap import Stores
from mythrix.core.chat import OllamaChatClient
from mythrix.core.config import Settings
from mythrix.core.ollama import create_chat_model, derive_chat_model

# A tool-calling turn needs more output headroom than a summarize call, whose
# reply is a paragraph. Scoped to the agent's own model so raising it never
# silently changes what `summarize_passage` returns.
_AGENT_NUM_PREDICT = 2048

# The fact-check call (ADR-025) returns a short JSON classification keyed by
# sentence index, never the answer's own text — a few lines regardless of how
# long the answer is, unlike the agent's own reply budget above.
_FACT_CHECK_NUM_PREDICT = 512


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
    surfacing on the first chat turn instead of at server startup.

    One chat model is constructed and every other role is derived from it:
    the narrow `ChatClient` the `summarize_passage` tool calls, the
    tool-bound model the graph's agent node calls, and the narrow
    `ChatClient` the fact-check node calls (ADR-025). Each derived role is a
    copy carrying its own output budget (`derive_chat_model`), sharing the
    original's already validated client — so the daemon is validated once
    per process, unless `fact_check_model` names a genuinely different
    model, in which case that one is validated separately."""
    if request.app.state.agent_graph is None:
        settings = Settings()
        stores = request.app.state.stores
        llm = create_chat_model(
            model=settings.agent_model or settings.generation_model or "",
            base_url=settings.ollama_base_url,
            num_ctx=settings.generation_num_ctx,
        )
        toolset = build_tools(stores, settings, OllamaChatClient(llm))
        agent_llm = derive_chat_model(llm, num_predict=_AGENT_NUM_PREDICT)

        if settings.fact_check_model and settings.fact_check_model != llm.model:
            fact_check_llm = create_chat_model(
                model=settings.fact_check_model,
                base_url=settings.ollama_base_url,
                num_ctx=settings.generation_num_ctx,
            )
        else:
            fact_check_llm = derive_chat_model(llm, num_predict=_FACT_CHECK_NUM_PREDICT)
        # A "thinking" model (e.g. qwen3) defaults to an internal reasoning pass
        # before responding; testing found that made this narrow classification
        # call slower for no benefit, so it's disabled for the role regardless
        # of which model is configured — a no-op for a model that has no such
        # mode. `format="json"` constrains Ollama's decoding to syntactically
        # valid JSON at the daemon level (ADR-025's classification design) —
        # belt-and-suspenders with `fact_check.py`'s own parser, which still
        # has to validate the schema (a well-formed but wrong-shaped object)
        # on top of it.
        fact_check_llm = derive_chat_model(fact_check_llm, reasoning=False, format="json")

        request.app.state.agent_graph = compile_agent_graph(
            agent_llm.bind_tools(toolset.model_tools),
            toolset,
            augment_max_regions=settings.augment_max_regions,
            augment_consolidation_group_size=settings.augment_consolidation_group_size,
            fact_check_chat_client=OllamaChatClient(fact_check_llm),
        )
    return request.app.state.agent_graph
