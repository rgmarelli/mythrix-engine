"""`GET /api/traditions`, `GET /api/symbols`, `GET /api/query` — see
`specs/query-viewer-web-ui/plan.md`'s "API package" and "Streaming design"
sections for the full contract each of these implements."""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from mythrix.api.dependencies import get_chat_client, get_stores
from mythrix.core.bootstrap import Stores
from mythrix.core.config import Settings
from mythrix.core.errors import MythrixError
from mythrix.core.models import ConceptCandidates, ConceptPairCandidates, GraphFacts, SignSummary, Tradition
from mythrix.core.query_service import stream_query
from mythrix.core.synthesis.chain import ChatClient
from mythrix.core.synthesis.prompts import render_passage_summary_prompt

router = APIRouter()


class DoneEventData(BaseModel):
    """Doc-only — describes the `done` SSE event's (empty) payload. Not
    constructed or validated anywhere; `stream_query`/`_sse_body` emit `{}`
    directly."""


class ErrorEventData(BaseModel):
    """Doc-only — describes the `error` SSE event's payload. Not
    constructed or validated anywhere; `_sse_body` emits `{"detail": ...}`
    directly."""

    detail: str


def _query_event_schema() -> dict:
    """A single JSON Schema describing every shape a `GET /api/query` SSE
    `data:` line can take — one per possible event type — for the OpenAPI
    `responses` entry below. `models_json_schema` merges each model's own
    `$defs` without collision, which hand-building this `anyOf` would risk
    (`GraphFacts`/`ConceptCandidates`/`ConceptPairCandidates` share nested
    `Source`/`Tradition`/`RetrievedPassage` definitions)."""
    event_models = (GraphFacts, ConceptCandidates, ConceptPairCandidates, DoneEventData, ErrorEventData)
    key_map, definitions = models_json_schema([(model, "serialization") for model in event_models])
    return {"anyOf": [key_map[(model, "serialization")] for model in event_models], **definitions}


@router.get("/traditions", response_model=list[Tradition])
def list_traditions(stores: Stores = Depends(get_stores)) -> list[Tradition]:
    return list(stores.graph_store.list_traditions())


@router.get("/symbols", response_model=list[SignSummary])
def list_symbols(stores: Stores = Depends(get_stores)) -> list[SignSummary]:
    return list(stores.graph_store.list_signs())


def _format_sse(event_type: str, payload: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_body(first_type: str, first_payload: dict, rest: Iterator[tuple[str, dict]]) -> Iterator[str]:
    yield _format_sse(first_type, first_payload)
    try:
        for event_type, payload in rest:
            yield _format_sse(event_type, payload)
    except MythrixError as exc:
        yield _format_sse("error", {"detail": str(exc)})
        return
    yield _format_sse("done", {})


@router.get(
    "/query",
    responses={
        200: {
            "description": (
                "A Server-Sent Events stream. Events, in order: `graph_facts` "
                "(payload shape: GraphFacts — one `sign`, one `manifestation`), "
                "zero or more `concept_candidates` (payload shape: ConceptCandidates "
                "— `concept`, `passages`, each passage carrying its own `source`/"
                "`tradition` inline), zero or more `pair_candidates` (payload shape: "
                "ConceptPairCandidates — `concepts`, `candidates`, each with "
                "`combined_score`/`matches`/`passage`), then exactly one of `done` "
                '(payload `{}`) or `error` (payload `{"detail": string}`).'
            ),
            "content": {"text/event-stream": {"schema": _query_event_schema()}},
        },
    },
)
def query(
    symbol: str,
    tradition: str,
    top_k: int | None = None,
    match_pool: int | None = None,
    stores: Stores = Depends(get_stores),
) -> StreamingResponse:
    """Streams one query's result as Server-Sent Events.

    Event sequence: `graph_facts` first, then one `concept_candidates` event
    per concept with at least one retrieved passage, then one
    `pair_candidates` event per convergence group, then `done`.

    A symbol/tradition/manifestation that doesn't exist raises before the
    stream opens — a normal `404` JSON response, handled by the registered
    `MythrixError` exception handler, same as `/api/traditions`/`/api/symbols`.
    A failure reachable only once retrieval is underway (e.g. the embedding
    model is unreachable) is reported as an `error` event instead, since the
    HTTP status is already committed to `200` by then.
    """
    settings = Settings()
    generator = stream_query(
        symbol=symbol,
        tradition=tradition,
        graph_store=stores.graph_store,
        vector_store=stores.vector_store,
        embedder=stores.embedder,
        top_k=top_k or settings.retrieval_top_k,
        match_pool_size=match_pool or settings.retrieval_match_pool_size,
        merge_top_k=settings.merge_top_k,
        min_score=settings.retrieval_min_score,
    )
    first_type, first_payload = next(generator)
    return StreamingResponse(_sse_body(first_type, first_payload, generator), media_type="text/event-stream")


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
