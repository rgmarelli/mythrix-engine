# Query Viewer Web UI — Spec

## Problem

`mythrix query` prints either a dense, truncated wall of text (passages cut to 500 characters, with no way to see the rest short of switching to `--json`) or raw JSON a human has to read by hand. Neither is navigable: there is no way to expand a passage to its full text and citation, or to browse graph facts, per-concept candidates, and concept-pair convergences as anything but flat scrolling output.

## Goals

- A web UI presenting the same evidentiary content `mythrix query --json` already produces — no new computation, a presentation layer only.
- A form to pick one symbol and one tradition, restricted to combinations that have an interpretation.
- Results organized into graph facts, per-concept candidate sections, and concept-pair convergence sections, rendered progressively as each becomes available.
- A dedicated panel to view a selected passage's full untruncated text and complete citation.
- A backend HTTP API, independent of the CLI process, reusing the existing retrieval pipeline and stores with no duplicated retrieval logic.

## Non-goals (v1)

- A web UI for `load-symbols`/`load-documents` — structured-data and document loading stay CLI-only.
- Authentication, multi-user access, or any access control.
- Write operations of any kind from the web UI.
- A conversational or chat-style interface. The AI Summary action (FR17-FR19) is a single-turn, stateless request per passage, not a conversation — it carries no history and no memory across requests.
- A UI for comparing multiple interpretive traditions of the same symbol against each other.
- Concurrent execution of the backend API process and a `load-symbols`/`load-documents` CLI invocation against the same `.mythrix/` directory.

## Functional requirements

### Web UI

- FR1: A web UI presents symbol query results equivalent to `mythrix query --json`'s evidentiary content, without requiring the CLI or reading raw JSON.
- FR2: The UI presents a form to select one symbol and one tradition, restricted to symbol/tradition combinations that have an interpretation.
- FR3: Submitting the form displays graph facts, then per-concept candidate passages, then concept-pair convergence groups for that symbol/tradition pair, each rendered as soon as it is available rather than only after the complete result is ready.
- FR4: Every displayed passage card shows its source attribution and score; passage text is never shown in the main results view, not even truncated — full verbatim text is available only after selecting the passage (FR5).
- FR5: A user can select a displayed passage to view its full verbatim text and complete citation/source detail in a dedicated panel, with no client-side truncation.
- FR6: Concept-pair convergence groups display each candidate's combined score and its per-concept component scores, distinguishing exact-value matches from semantic-similarity matches.
- FR16: For each correspondence shown in graph facts, the display includes the target symbol's own intrinsic properties and any semantic facts recorded for that correspondence, not only the correspondence claim itself.

### AI Summary

- FR17: A user can request an AI-generated summary of a selected passage, scoped to the concept(s) it was retrieved for.
- FR18: A summary request sends only the selected passage's retrieved text and its associated concept(s) to the generation model — no graph facts, no other passages.
- FR19: A summarization request that cannot reach the generation model returns a distinct, client-visible error, without altering or clearing the already-displayed query result.

### Backend API

- FR7: A backend HTTP API serves symbol/tradition listings and query results as JSON, as a process independent of the CLI.
- FR8: The backend API executes queries through the existing retrieval pipeline and graph/vector stores, with no duplicated graph-query or retrieval logic.
- FR9: A query naming an unknown symbol, an unknown tradition, or a symbol/tradition pair without an interpretation returns a distinct, client-visible error.
- FR10: A query that cannot reach the embedding model returns a distinct, client-visible error.
- FR15: The query endpoint delivers its result as a sequence of discrete events — graph facts, one event per concept, one event per concept pair — over a single streamed HTTP response, not as one combined JSON payload returned only after every concept and pair has been retrieved.

### Deployment and scope boundaries

- FR11: The web frontend is a separate, independently buildable application from the Python package, within the same repository.
- FR12: Loading structured data or documents is not exposed in the web UI.
- FR13: A production build of the frontend can be served by the backend API process.
- FR14: The backend API process and a `load-symbols`/`load-documents` CLI invocation do not run concurrently against the same graph database path.
