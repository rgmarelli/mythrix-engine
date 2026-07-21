"""`GET /api/traditions`, `GET /api/symbols`, `GET /api/query`,
`POST /api/reload-symbols` — see `specs/convergence-rollup-retrieval/plan.md`
for `/api/query`'s `RegionQueryResult` contract, and
`specs/query-viewer-web-ui/plan.md`'s "API package" section for the other
GET routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from mythrix.api.dependencies import get_chat_client, get_stores
from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings
from mythrix.core.loaders.sign_loader import load_directory, summarize_plan
from mythrix.core.models import RegionQueryResult, SignSummary, Tradition
from mythrix.core.query_service import query_regions
from mythrix.core.synthesis.chain import ChatClient
from mythrix.core.synthesis.prompts import render_passage_summary_prompt

router = APIRouter()


@router.get("/traditions", response_model=list[Tradition])
def list_traditions(stores: Stores = Depends(get_stores)) -> list[Tradition]:
    return list(stores.graph_store.list_traditions())


@router.get("/symbols", response_model=list[SignSummary])
def list_symbols(stores: Stores = Depends(get_stores)) -> list[SignSummary]:
    return list(stores.graph_store.list_signs())


@router.get("/query", response_model=RegionQueryResult)
def query(
    symbol: str,
    tradition: str,
    top_k: int | None = None,
    match_pool: int | None = None,
    min_score: float | None = None,
    stores: Stores = Depends(get_stores),
) -> RegionQueryResult:
    """Returns one query's facets and ranked region list
    (`convergence-rollup-retrieval`).

    `min_score` overrides `Settings.retrieval_min_score` (default `0.45`) for
    this request only — checked with `is None`, not truthiness, since `0.0`
    is itself a meaningful explicit value (pass `min_score=0` to disable the
    floor entirely for one request).

    A symbol/tradition/manifestation that doesn't exist, or a failure
    reaching the embedding model, is handled by the registered
    `MythrixError` exception handler, same as `/api/traditions`/`/api/symbols`
    (404/502 JSON).
    """
    settings = Settings()
    return query_regions(
        symbol=symbol,
        tradition=tradition,
        graph_store=stores.graph_store,
        vector_store=stores.vector_store,
        embedder=stores.embedder,
        top_k=top_k or settings.retrieval_top_k,
        match_pool_size=match_pool or settings.retrieval_match_pool_size,
        merge_top_k=settings.merge_top_k,
        min_score=min_score if min_score is not None else settings.retrieval_min_score,
        region_window_size=settings.region_window_size,
        region_min_interpretants=settings.region_min_interpretants,
    )


class ReloadSymbolsResponse(BaseModel):
    traditions: int
    sources: int
    signs: int
    manifestations: int
    intersemiotic_interpretants: int


@router.post("/reload-symbols", response_model=ReloadSymbolsResponse)
def reload_symbols(path: str | None = None, stores: Stores = Depends(get_stores)) -> ReloadSymbolsResponse:
    """Re-reads every tradition/source/sign YAML under `path` (default
    `Settings.symbols_data_path`) and upserts it into the graph store `Stores`
    already holds open for the process's full lifetime (`app.py`'s
    `lifespan`) — no second Kùzu connection is opened, so, unlike
    `mythrix load-symbols` against the same `.mythrix/` directory, this works
    with the API server running (see `specs/query-viewer-web-ui/plan.md`'s
    Kùzu single-writer note).

    Writes land as each `store.upsert_*` call runs, not in one transaction —
    a request already in flight against `/api/query`/`/api/symbols` can
    observe a partially-reloaded graph. Acceptable for a local, single-user
    dev tool; not a guarantee to build on for a multi-user deployment.

    `IngestValidationError` (bad YAML, an unresolvable reference, a duplicate
    slug) leaves the graph untouched (FR5) and is handled by the registered
    `MythrixError` exception handler (422), same mechanism as every other
    route's errors.
    """
    settings = Settings()
    root = Path(path) if path else settings.symbols_data_path
    plan = load_directory(root, stores.graph_store)
    return ReloadSymbolsResponse(**summarize_plan(plan))


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
    which invokes no generation model (FR29). `ModelUnavailableError`/
    `ModelRequestError` raised by `get_chat_client`/`chat_client.invoke` are
    handled by the same registered `MythrixError` exception handler as every
    other route (502)."""
    prompt = render_passage_summary_prompt(payload.passage_text, tuple(payload.concepts))
    return SummarizeResponse(summary=chat_client.invoke(prompt))
