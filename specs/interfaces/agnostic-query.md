# Agnostic (Ad-hoc) Interpretant Query

A conversational-agent capability, scoped by [ADR-010](../architecture-decisions/adr-010-agnostic-adhoc-interpretant-query.md), letting a user search the corpus directly on a list of their own terms — no Sign or Tradition named — reusing the existing directive vocabulary curated interpretants already carry ([retrieval.md](../retrieval/retrieval.md) FR-RT-15, FR-RT-17–19). This document specifies the agent-side path up through handing back an execution instruction, and the dedicated endpoint that actually performs the query. How a consumer learns to execute that instruction is specified in [agent-capabilities.md](agent-capabilities.md); how the web viewer renders the result is specified in [web-viewer.md](web-viewer.md).

## Vocabulary

- **ad-hoc term**: A user-authored token parsed from a `/query` chat command, optionally carrying one directive suffix (`:exact`, `:filter`).
- **directive**: The same `"exact"`/`"filter"` vocabulary [retrieval.md](../retrieval/retrieval.md)'s `QueryDirective` already defines for curator-authored interpretants — here authored by the user instead. An undecorated term is an ordinary concept.
- **instruction**: A structured, transport-agnostic descriptor (`{"type": ..., "payload": ...}`) returned in the agent's `instructions` field, naming an action for a consumer to take.
- **pending ad-hoc query**: A parsed term list held in session state under a backend-generated id, awaiting confirmation. It is not a query result and nothing has been retrieved for it.
- **ad-hoc query**: A region query ([ranking.md](../retrieval/ranking.md)) run against a synthetic, sentinel `GraphFacts` built from ad-hoc terms, rather than one resolved from the Sign Graph.

## Functional requirements

### Command recognition and parsing

- FR-AQ-01: A chat message beginning with `/query` is recognized as a request to run an ad-hoc interpretant query. Recognition and everything that follows from it are deterministic and invoke no generation model.
- FR-AQ-02: The message's remainder is parsed as a comma-separated list of terms; each term optionally carries one directive suffix, `:exact` or `:filter`. An undecorated term is always treated as an ordinary concept. Parsing is performed by the backend, never by the model.
- FR-AQ-03: A `/query` command naming no terms, or naming a directive outside `:exact`/`:filter`, produces a reply identifying the problem and restating the accepted syntax. No pending ad-hoc query is created and no instruction is emitted.

### Confirmation

- FR-AQ-04: Parsing a valid `/query` command creates a pending ad-hoc query under a backend-generated id and ends the turn. Nothing is retrieved and no ad-hoc query is executed at this step.
- FR-AQ-05: A session holds at most one pending ad-hoc query: a subsequent `/query` command replaces it, and a thread reset ([agent.md](agent.md) FR-AG-16) discards it.
- FR-AQ-06: The turn that creates a pending ad-hoc query replies with the parsed term/directive list restated back to the user, and names the exact command required to confirm it — so the flow is completable without any consumer that interprets instructions.
- FR-AQ-07: The same turn emits a `confirm_query` instruction carrying the pending query's id, its parsed terms, and the confirmation command a consumer should send to confirm.
- FR-AQ-08: A chat message beginning with `/query-confirm` is recognized as a confirmation and is handled deterministically, invoking no generation model.
- FR-AQ-09: An ad-hoc query is executed only when a `/query-confirm` command names the id of a currently-pending ad-hoc query in that session. No other message confirms one, regardless of its wording; no message is inspected for affirmative intent.
- FR-AQ-10: The terms executed are taken from the stored pending ad-hoc query, never from the confirming message.
- FR-AQ-11: A `/query-confirm` command naming an unknown, already-used, or discarded id produces a reply saying so. Nothing is executed and no instruction is emitted.
- FR-AQ-12: Confirming consumes the pending ad-hoc query: the same id cannot confirm a second time.

### Execution instruction

- FR-AQ-13: A confirmed ad-hoc query emits an `execute_query` instruction carrying the confirmed term/directive list. The turn itself performs no retrieval and accesses neither the graph store nor the vector store.
- FR-AQ-14: An instruction carries no HTTP method, path, or other transport detail. How its `type` maps to an actual endpoint call is declared once by the backend in the capabilities document ([agent-capabilities.md](agent-capabilities.md) FR-CAP-07–FR-CAP-12), not restated per instruction and not decided by the consumer.
- FR-AQ-15: Instructions are populated by the backend directly from the deterministic command handling that produced them, never parsed or inferred from a model-authored reply.
- FR-AQ-22: An `execute_query` instruction's payload is a valid request body for the ad-hoc query endpoint (FR-AQ-18) as sent, requiring no reshaping by the consumer.

### Isolation from the conversation

- FR-AQ-16: `/query` and `/query-confirm` turns add nothing to the agent's conversation history. An ordinary turn's model input is identical to what it would have been had those commands never been sent.
- FR-AQ-17: This capability adds no tool to the agent's tool set ([agent.md](agent.md) FR-AG-03) and no rule to its system prompt ([agent.md](agent.md) FR-AG-28, FR-AG-32).

### Ad-hoc retrieval

- FR-AQ-18: A dedicated, non-agent endpoint accepts a term/directive list and performs the actual ad-hoc query, independent of the agent — directly callable (e.g. by a frontend, or by a test) without going through a chat turn. It is a read: the request carries its term list as content because the list is structured, not because anything is created or modified, and repeating the request changes nothing.
- FR-AQ-19: An ad-hoc query builds a synthetic `GraphFacts` from the supplied terms: one interpretant per term — a plain concept interpretant for an undirected term, or one carrying the term's directive (with the term's own text as its literal token) for a directive term — attached to a sentinel sign/tradition/manifestation that names no real semiotic system, sign, or tradition.
- FR-AQ-20: That synthetic `GraphFacts` is passed unmodified into the existing region-query pipeline ([retrieval.md](../retrieval/retrieval.md), [ranking.md](../retrieval/ranking.md)); every existing region-matching, ranking, and directive-handling requirement (FR-RT-10–20) applies, with no new matching or ranking behavior introduced by this path.
- FR-AQ-21: An ad-hoc query result is unambiguously distinguishable from a graph-native one — its sentinel sign/tradition identifiers name no entry in the Sign Graph — so a consumer can never mistake it for curated content.

## Non-goals

- Any consumer-side behavior: which instruction a consumer acts on, how it executes one, and how it renders the result belong to [agent-capabilities.md](agent-capabilities.md) and [web-viewer.md](web-viewer.md). This spec covers the backend/agent-side path through emitting the instructions, and the endpoint's own request/response contract.
- Understanding a confirmation expressed in natural language ("yes", "go ahead"). Confirmation is the `/query-confirm` command and nothing else (see [ADR-010](../architecture-decisions/adr-010-agnostic-adhoc-interpretant-query.md) alternatives).
- Any agent awareness of ad-hoc queries: the agent cannot discuss, refer back to, or answer questions about a query run through this path, and does not narrate its results.
- Expiring a pending ad-hoc query on a timer. It lives until replaced, confirmed, or discarded by a thread reset.
- Any directive beyond `"exact"`/`"filter"` — a `"skip"`-equivalent has no meaningful use for a term the user is explicitly, deliberately including.
- Any change to `query_regions` or graph-native retrieval/ranking behavior.
- Persisting a pending ad-hoc query, its terms, or its result across a backend process restart, consistent with the rest of agent session/context state ([agent.md](agent.md) FR-AG-20).
