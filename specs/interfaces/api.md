# Backend API

The independent HTTP process that serves [Retrieval](../retrieval/retrieval.md)/[Ranking](../retrieval/ranking.md) results to the [Web Viewer](web-viewer.md) and hosts the [Conversational Agent](agent.md).

## Functional requirements

- FR-API-01: A backend HTTP API, a process independent of the CLI, serves sign/tradition listings and region query results as JSON, executed through the existing retrieval pipeline and graph/vector stores with no duplicated graph-query or retrieval logic. A web viewer presents this content without requiring the CLI or reading raw JSON.
- FR-API-02: An API endpoint re-reads structured sign/tradition/source data from disk and upserts it into the graph store already open for the running API process, without requiring the process to be restarted. Invalid structured data leaves the graph unchanged and returns a distinct, client-visible error. This endpoint is not exposed in the web viewer.
- FR-API-03: Loading structured data or documents is not exposed in the web viewer — `load-symbols`/`load-documents` stay CLI-only (FR-API-02's reload endpoint is a distinct, narrower capability: reloading structured data into an already-running process, not a general-purpose loader UI).

Segment-range retrieval (`GET /api/segments`) is specified in [context-expansion.md](../retrieval/context-expansion.md) FR-CE-11; passage summarization (`POST /api/summarize`) is specified in [agent.md](agent.md) FR-AG-03.

## Non-goals

- Authentication, multi-user access, or any access control on the web viewer or backend API.
- Write operations from the web viewer beyond the structured-data reload endpoint (FR-API-02) — loading structured data or documents from scratch stays CLI-only (FR-API-03).
- Concurrent execution of the backend API process and a `load-symbols`/`load-documents` CLI invocation against the same graph/vector store paths (FR-WEB-05) — each opens its own connection to the graph database's single-writer lock; the reload endpoint (FR-API-02) is exempt, since it reuses the API process's already-open connection rather than opening a second one.
