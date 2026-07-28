"""`GET /api/traditions`, `GET /api/signs`, `GET /api/query`,
`POST /api/reload-signs` — see `specs/retrieval/ranking.md`
for `/api/query`'s `RegionQueryResult` contract, and
`specs/interfaces/api.md` for the other
GET routes."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import APIRouter, Depends
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from mythrix.agent.context import AgentUiSelection
from mythrix.agent.sessions import SessionStore
from mythrix.agent.turn_service import AgentTurnResponse, run_chat_turn
from mythrix.api.dependencies import get_agent_graph, get_agent_sessions, get_chat_client, get_stores
from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings
from mythrix.core.errors import MythrixError
from mythrix.core.loaders.sign_loader import load_directory, summarize_plan
from mythrix.core.models import AdhocTerm, RegionQueryResult, Segment, SignSummary, Tradition
from mythrix.core.query_service import execute_adhoc_query, fetch_source_segments, query_regions
from mythrix.core.synthesis.chain import ChatClient
from mythrix.core.synthesis.prompts import render_passage_summary_prompt

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/traditions", response_model=list[Tradition])
def list_traditions(stores: Stores = Depends(get_stores)) -> list[Tradition]:
    return list(stores.graph_store.list_traditions())


@router.get("/signs", response_model=list[SignSummary])
def list_signs(stores: Stores = Depends(get_stores)) -> list[SignSummary]:
    return list(stores.graph_store.list_signs())


@router.get("/query", response_model=RegionQueryResult)
def query(
    sign: str,
    tradition: str,
    top_k: int | None = None,
    match_pool: int | None = None,
    min_score: float | None = None,
    stores: Stores = Depends(get_stores),
) -> RegionQueryResult:
    """Returns one query's facets and ranked region list
    (see `specs/retrieval/ranking.md`).

    `min_score` overrides `Settings.retrieval_min_score` (default `0.6`) for
    this request only — checked with `is None`, not truthiness, since `0.0`
    is itself a meaningful explicit value (pass `min_score=0` to disable the
    floor entirely for one request).

    A sign/tradition/manifestation that doesn't exist, or a failure
    reaching the embedding model, is handled by the registered
    `MythrixError` exception handler, same as `/api/traditions`/`/api/signs`
    (404/502 JSON).
    """
    settings = Settings()
    effective_top_k = top_k or settings.retrieval_top_k
    effective_match_pool_size = match_pool or settings.retrieval_match_pool_size
    effective_min_score = min_score if min_score is not None else settings.retrieval_min_score

    start = time.perf_counter()
    try:
        result = query_regions(
            sign=sign,
            tradition=tradition,
            graph_store=stores.graph_store,
            vector_store=stores.vector_store,
            embedder=stores.embedder,
            top_k=effective_top_k,
            match_pool_size=effective_match_pool_size,
            merge_top_k=settings.merge_top_k,
            min_score=effective_min_score,
            region_window_size=settings.region_window_size,
            region_min_interpretants=settings.region_min_interpretants,
        )
    except MythrixError as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info("query failed: sign=%s tradition=%s duration_ms=%.1f error=%s", sign, tradition, duration_ms, exc)
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    scores = [region.score for region in result.regions]
    score_range = f"{min(scores):.3f}-{max(scores):.3f}" if scores else "n/a"
    logger.info(
        "query: sign=%s tradition=%s top_k=%d match_pool=%d min_score=%.3f duration_ms=%.1f regions=%d score_range=%s",
        sign,
        tradition,
        effective_top_k,
        effective_match_pool_size,
        effective_min_score,
        duration_ms,
        len(result.regions),
        score_range,
    )
    return result


class AdhocQueryRequest(BaseModel):
    terms: list[AdhocTerm]
    top_k: int | None = None
    match_pool: int | None = None
    min_score: float | None = None


@router.post("/query/adhoc", response_model=RegionQueryResult)
def query_adhoc(request: AdhocQueryRequest, stores: Stores = Depends(get_stores)) -> RegionQueryResult:
    """Runs a region query against a user-supplied, graph-independent term
    list rather than a resolved sign/tradition (`specs/interfaces/agnostic-query.md`
    FR-AQ-09, ADR-010). Same defaulting/error-handling/logging shape as `GET /api/query`; an
    empty `terms` list is rejected the same way an unknown sign is — via the
    registered `MythrixError` exception handler (422)."""
    settings = Settings()
    effective_top_k = request.top_k or settings.retrieval_top_k
    effective_match_pool_size = request.match_pool or settings.retrieval_match_pool_size
    effective_min_score = request.min_score if request.min_score is not None else settings.retrieval_min_score

    start = time.perf_counter()
    try:
        result = execute_adhoc_query(
            terms=request.terms,
            graph_store=stores.graph_store,
            vector_store=stores.vector_store,
            embedder=stores.embedder,
            top_k=effective_top_k,
            match_pool_size=effective_match_pool_size,
            merge_top_k=settings.merge_top_k,
            min_score=effective_min_score,
            region_window_size=settings.region_window_size,
            region_min_interpretants=settings.region_min_interpretants,
        )
    except MythrixError as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info("adhoc query failed: terms=%d duration_ms=%.1f error=%s", len(request.terms), duration_ms, exc)
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "adhoc query: terms=%d top_k=%d match_pool=%d min_score=%.3f duration_ms=%.1f regions=%d",
        len(request.terms),
        effective_top_k,
        effective_match_pool_size,
        effective_min_score,
        duration_ms,
        len(result.regions),
    )
    return result


@router.get("/segments", response_model=list[Segment])
def source_segments(
    source_id: str,
    start_ordinal: int,
    end_ordinal: int,
    stores: Stores = Depends(get_stores),
) -> list[Segment]:
    """A contiguous ordinal range of one source's segments, verbatim — the
    coordinate lookup behind the web UI's Add Context action
    (`specs/retrieval/context-expansion.md`), distinct from `/api/query`:
    no embedding model is invoked and no similarity ranking happens, just a
    range read against the vector store.

    An unknown `source_id` is handled by the registered `MythrixError`
    exception handler (404), same mechanism as every other route's errors.
    """
    return list(
        fetch_source_segments(
            source_id=source_id,
            start_ordinal=start_ordinal,
            end_ordinal=end_ordinal,
            graph_store=stores.graph_store,
            vector_store=stores.vector_store,
        )
    )


class ReloadSignsResponse(BaseModel):
    traditions: int
    sources: int
    signs: int
    manifestations: int
    intersemiotic_interpretants: int


@router.post("/reload-signs", response_model=ReloadSignsResponse)
def reload_signs(path: str | None = None, stores: Stores = Depends(get_stores)) -> ReloadSignsResponse:
    """Re-reads every tradition/source/sign YAML under `path` (default
    `Settings.signs_data_path`) and upserts it into the graph store `Stores`
    already holds open for the process's full lifetime (`app.py`'s
    `lifespan`) — no second Kùzu connection is opened, so, unlike
    `mythrix load-signs` against the same `.mythrix/` directory, this works
    with the API server running (see `specs/interfaces/api.md` Non-goals'
    Kùzu single-writer note).

    Writes land as each `store.upsert_*` call runs, not in one transaction —
    a request already in flight against `/api/query`/`/api/signs` can
    observe a partially-reloaded graph. Acceptable for a local, single-user
    dev tool; not a guarantee to build on for a multi-user deployment.

    `IngestValidationError` (bad YAML, an unresolvable reference, a duplicate
    slug) leaves the graph untouched (FR-SD-02) and is handled by the registered
    `MythrixError` exception handler (422), same mechanism as every other
    route's errors.
    """
    settings = Settings()
    root = Path(path) if path else settings.signs_data_path
    plan = load_directory(root, stores.graph_store)
    return ReloadSignsResponse(**summarize_plan(plan))


class SummarizeRequest(BaseModel):
    passage_text: str
    concepts: list[str]


class SummarizeResponse(BaseModel):
    summary: str


@router.post("/summarize", response_model=SummarizeResponse)
def summarize_passage(
    payload: SummarizeRequest, chat_client: ChatClient = Depends(get_chat_client)
) -> SummarizeResponse:
    """One ad-hoc generation call for a single already-retrieved passage,
    triggered by the web UI's AI Summary button — distinct from `/api/query`,
    which invokes no generation model (FR-RT-10). `ModelUnavailableError`/
    `ModelRequestError` raised by `get_chat_client`/`chat_client.invoke` are
    handled by the same registered `MythrixError` exception handler as every
    other route (502)."""
    prompt = render_passage_summary_prompt(payload.passage_text, tuple(payload.concepts))
    return SummarizeResponse(summary=chat_client.invoke(prompt))


class AgentTurnRequest(BaseModel):
    session_id: str
    message: str
    ui_selection: AgentUiSelection


@router.post("/agent", response_model=AgentTurnResponse)
def agent_turn(
    payload: AgentTurnRequest,
    sessions: SessionStore = Depends(get_agent_sessions),
    graph: CompiledStateGraph = Depends(get_agent_graph),
) -> AgentTurnResponse:
    """One turn of the in-app chat panel (`specs/interfaces/agent.md` FR-AG-14–FR-AG-22):
    the browser sends its message plus its current UI selection, as-is, each
    turn; the backend detects a thread reset, runs the agent loop, and
    returns the three-part response (updated context, grounded reply text,
    structured cards) plus `thread_reset`. `ModelUnavailableError`/
    `ModelRequestError` raised by `get_agent_graph`'s lazy build are handled
    by the same registered `MythrixError` exception handler as every other
    route (502)."""
    settings = Settings()
    return run_chat_turn(
        graph=graph,
        sessions=sessions,
        session_id=payload.session_id,
        message=payload.message,
        ui_selection=payload.ui_selection,
        max_tool_iterations=settings.agent_max_tool_iterations,
    )
