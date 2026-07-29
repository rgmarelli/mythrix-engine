# Backend API

The independent HTTP process that serves [Retrieval](../retrieval/retrieval.md)/[Ranking](../retrieval/ranking.md) results to the [Web Viewer](web-viewer.md) and hosts the [Conversational Agent](agent.md).

## Functional requirements

- FR-API-01: A backend HTTP API, a process independent of the CLI, serves sign/tradition listings and region query results as JSON, executed through the existing retrieval pipeline and graph/vector stores with no duplicated graph-query or retrieval logic. It is the only surface that answers a query; the CLI loads data only. A web viewer presents this content without reading raw JSON.
- FR-API-02: An API endpoint re-reads structured sign/tradition/source data from disk and upserts it into the graph store already open for the running API process, without requiring the process to be restarted. Invalid structured data leaves the graph unchanged and returns a distinct, client-visible error. This endpoint is not exposed in the web viewer.
- FR-API-03: Loading structured data or documents is not exposed in the web viewer — `load-signs`/`load-documents` stay CLI-only (FR-API-02's reload endpoint is a distinct, narrower capability: reloading structured data into an already-running process, not a general-purpose loader UI).
- FR-API-04: Every `GET /api/query` request logs its parameters, duration, region count, and result score range to the process's standard log output at INFO level, for local debugging — including, per concept reachable from the queried sign and per recognized filter token, the query variants run and the number of results reaching the score floor. This is operational visibility only; it adds no visible behavior for the caller and never changes the response.

Segment-range retrieval (`GET /api/segments`) is specified in [context-expansion.md](../retrieval/context-expansion.md) FR-CE-11; ad-hoc region queries (`QUERY /api/query/adhoc`, [RFC 10008](https://www.rfc-editor.org/rfc/rfc10008.html)) are specified in [agnostic-query.md](agnostic-query.md) FR-AQ-18; the agent capabilities document (`GET /api/agent/capabilities`) is specified in [agent-capabilities.md](agent-capabilities.md) FR-CAP-01.

- FR-API-05: The chat-turn endpoint delivers a turn as a sequence of newline-delimited JSON events ending in exactly one terminal event carrying the turn's context, reply text, instructions and thread-reset flag ([augmentation.md](augmentation.md) FR-AU-22). Every turn uses this shape, so there is one turn transport rather than a streaming one and a non-streaming one whose bodies must be kept equal ([ADR-015](../architecture-decisions/adr-015-deterministic-augmentation-over-viewer-regions.md)). A failure arising before the response body begins is an HTTP error as for every other route; a failure after that is reported within the event sequence.

## Non-goals

- Authentication, multi-user access, or any access control on the web viewer or backend API.
- Write operations from the web viewer beyond the structured-data reload endpoint (FR-API-02) — loading structured data or documents from scratch stays CLI-only (FR-API-03).
- Concurrent execution of the backend API process and a `load-signs`/`load-documents` CLI invocation against the same graph/vector store paths (FR-WEB-05) — each opens its own connection to the graph database's single-writer lock; the reload endpoint (FR-API-02) is exempt, since it reuses the API process's already-open connection rather than opening a second one.
