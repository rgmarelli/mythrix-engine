# Agent Operator — Spec

## Problem

Operating Mythrix today is a sequence of discrete, manual actions. A researcher
picks a semiotic system, a sign, and a tradition; runs a query (`mythrix query`
or `GET /api/query`); reads the ranked hotspots; separately fetches surrounding
context; and optionally requests a single-turn summary. Each step is its own CLI
invocation or UI interaction, and nothing carries state from one step to the
next. There is no conversational surface that accepts a natural-language request,
plans which retrieval operations satisfy it, executes them against the existing
engine, and reports back with citations — the "conversational agent layer"
anticipated by the master spec (`specs/spec.md`, Non-goals; FR11, FR12) but not
yet built.

## Vocabulary

- **semiotic system** — the top-level symbol domain a sign belongs to
  (`Sign.semiotic_system`, e.g. `tarot`, `hebrew_alef_bet`). It scopes which
  signs, and therefore which traditions, are in play.
- **agent** — a tool-calling loop, driven by a local chat model, that turns a
  natural-language request into calls against Mythrix's existing operations and
  reports the results conversationally.
- **tool** — a single, typed, read-only operation the agent may invoke, wrapping
  an existing Mythrix service function (e.g. run a query, fetch a segment range).
- **turn** — one user message plus the agent's full response to it, including any
  tool calls made while producing that response.
- **session** — an ordered series of turns sharing conversation history.
- **tool trace** — the ordered record of which tools the agent called during a
  turn, surfaced to the user so the evidence path is visible.

## Goals

- A conversational **CLI surface** (`mythrix-agent`) that runs an interactive
  agent loop: the user types requests, the agent calls tools and answers, and
  history persists across turns within the session.
- The agent operates Mythrix exclusively through a fixed set of **read-only
  tools** that wrap existing service functions — discovery (semiotic systems,
  traditions, symbols), single-symbol facts lookup, region query, segment-range
  fetch, and passage summarization.
- Discovery is **scoped by semiotic system**: when a request is ambiguous about
  which semiotic system to use, the agent asks the user which one rather than
  guessing or listing across all of them.
- Every factual claim the agent makes about symbols or evidence is grounded in a
  tool result and carries the citation that the tool returned; the agent invents
  no symbols, interpretants, or interpretations.
- The agent runs on a **local generation model only** (Ollama), consistent with
  the project's local-only stance.
- The underlying retrieval remains deterministic and embedding-only: the agent's
  generation model does conversation and tool selection, and does not participate
  in deciding what a retrieval result is (master FR11).

## Non-goals

- A web or chat-style UI. A `POST /api/agent` endpoint and a browser chat panel
  are a separate, later feature; this feature ships the CLI surface only.
- Any mutating or administrative operation. The agent cannot ingest symbols or
  documents, reload the graph, or otherwise write to the stores. Ingestion
  remains the existing `load-symbols` / `load-documents` / `reload-symbols`
  paths, invoked by a human.
- Changing retrieval, ranking, convergence scoring, facets, or what counts as a
  match. The agent is an orchestration and presentation layer over the existing
  query path; it introduces no new retrieval behavior.
- A cloud or hosted generation model. The agent uses local Ollama only.
- Persisting sessions across process restarts. Conversation history lives only
  for the duration of a running `mythrix-agent` process.
- Free-text natural-language *parsing into retrieval query text*. Similarity
  search is still driven from graph facts (master FR8); the agent chooses which
  sign/tradition to query, but the query text is derived by the existing
  pipeline, never from raw user prose.

## Functional requirements

- FR1: The system provides a `mythrix-agent` command — a console script separate
  from the `mythrix` CLI — that starts an interactive, multi-turn conversational
  session in the terminal and reads successive user requests until the user exits.
- FR2: The agent answers each request by invoking one or more read-only tools and
  composing their results into a natural-language reply. It maintains
  conversation history across turns within a session.
- FR3: The agent has access to exactly these tools, each wrapping an existing
  service function and returning structured data (not prose):
  - **list semiotic systems** — the available semiotic systems.
  - **list traditions** — the available traditions, optionally scoped to one
    semiotic system.
  - **list symbols** — the available signs, optionally scoped to one semiotic
    system.
  - **get symbol** — retrieve one named sign's facts (e.g. "The Magician"): its
    canonical name, semiotic system, intrinsic properties, and, for a given
    tradition, its manifestation's interpretants, denotation, correspondences,
    and citations (built from `KuzuGraphStore.get_manifestation`). This is a
    graph-facts lookup, not a corpus retrieval — it runs no similarity search.
  - **query symbol** — run a region (hotspot) query for a given sign and
    tradition, returning ranked regions with their matched interpretants,
    verbatim segment text, and citations (the same operation as `GET /api/query`).
  - **fetch segments** — retrieve a contiguous ordinal range of one source's
    segments verbatim, by structural coordinate, running no similarity search
    (the same operation as `GET /api/segments`).
  - **summarize passage** — produce a single-turn summary of supplied passage
    text scoped to supplied interpretants, using the generation model (the same
    operation as `POST /api/summarize`).
- FR4: The registered tool set contains no operation that writes to, mutates, or
  reloads either store. Read-only is a structural property of the tool set, not a
  runtime check.
- FR5: When a request to list traditions or symbols, or to get or query a
  symbol, does not determine which semiotic system to use and the choice is
  ambiguous (more than one semiotic system exists and the request names none),
  the agent asks the user which semiotic system to use — offering the available
  ones from the list-semiotic-systems tool — before listing or retrieving,
  rather than guessing or silently listing across all systems. Once a semiotic
  system is established in the conversation, the agent may reuse it for
  subsequent turns without re-asking.
- FR6: The agent must not state any symbol, interpretant, tradition, source, or
  passage as fact unless it appears in a tool result from the current session,
  and it must carry through the citation/locator the tool returned. It must not
  fabricate or infer symbols or interpretations absent from tool results.
- FR7: When get_symbol returns needs_tradition (no interpretive content, only
  the sign's available traditions), the system presents the tradition choices
  to the user deterministically, without generation-model involvement — the
  generation model is not invoked to compose that turn's reply. This guarantees
  FR6 cannot be violated in this specific case regardless of model behavior,
  since a tradition list is the entirety of what the tool returned and needs no
  model composition.
- FR8: The agent's generation model is a local Ollama model. When no generation
  model is configured or the model cannot be reached, the command reports a
  distinct, actionable error rather than proceeding.
- FR9: The retrieval a tool triggers invokes no generation model and is
  unchanged from the existing query path (master FR29): the generation model is
  used only for the agent's own conversation/tool-selection and for the explicit
  summarize tool.
- FR10: Each turn surfaces a tool trace — which tools the agent called, in order —
  so the user can see the evidence path behind the answer.
- FR11: A tool that fails (e.g. an unknown sign or tradition, an unreachable model
  for summarization) returns a distinct error to the agent that the agent relays
  to the user, without terminating the session; the user can continue with
  further turns.
- FR12: The agent loop is bounded: a single turn cannot invoke tools indefinitely.
  On reaching the bound, the turn ends with a clear message rather than looping.
- FR13: The agent is additive and self-contained. It ships as a separate
  `mythrix-agent` console script and adds no command to the `mythrix` CLI; the
  existing `query`, `load-symbols`, and `load-documents` commands and all
  `/api/*` routes are unchanged in behavior and output.
